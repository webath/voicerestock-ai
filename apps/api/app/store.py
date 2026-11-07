"""State σε SQLite: suggestions (JSON), confirmation tokens, idempotency, calls, audit.

Όλες οι αλλαγές περνάνε από εδώ με ένα lock — μία διεργασία uvicorn είναι αρκετή για το demo.
"""
from __future__ import annotations

import hashlib
import copy
from datetime import datetime, timezone
import json
import os
import sqlite3
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROCESSED = Path(os.environ.get("PROCESSED_DIR", ROOT / "data" / "processed"))
DB_PATH = Path(os.environ.get("API_DB", PROCESSED / "app_state.sqlite"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS suggestions (id TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tokens (token TEXT PRIMARY KEY, suggestion_id TEXT NOT NULL, version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS idempotency (key TEXT PRIMARY KEY, response TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS calls (call_sid TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, actor TEXT, action TEXT,
                                  suggestion_id TEXT, outcome TEXT, correlation_id TEXT);
CREATE TABLE IF NOT EXISTS forecast_seeds (id TEXT PRIMARY KEY, body TEXT NOT NULL);
"""


def _price_list() -> dict[int, float]:
    import csv
    with open(ROOT / "team_pack" / "data" / "MTRL.csv", encoding="utf-8-sig", newline="") as f:
        return {int(r["MTRL"]): float(r["PRICER"]) for r in csv.DictReader(f)}


PRICES = _price_list()


def with_value(s: dict) -> dict:
    """Αξία (€, καθαρή, τιμή καταλόγου 2026 × ποσότητα). Υπολογίζεται σε κάθε ανάγνωση → ακολουθεί τις αλλαγές ποσότητας."""
    total = 0.0
    for l in s["LINES"]:
        l["PRICE"] = PRICES.get(l["MTRL"])
        l["LINE_VALUE"] = round((l["PRICE"] or 0) * l["QTY1"], 2)
        total += l["LINE_VALUE"]
    s["VALUE"] = round(total, 2)
    return s


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Store:
    def __init__(self, db_path: Path = DB_PATH, seed_path: Path = PROCESSED / "suggestions.json"):
        self.lock = threading.RLock()
        self.seed_path = seed_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.executescript(SCHEMA)
        if "snapshot" not in {r[1] for r in self.db.execute("PRAGMA table_info(audit)")}:
            self.db.execute("ALTER TABLE audit ADD COLUMN snapshot TEXT")
        stored = self.db.execute("SELECT value FROM meta WHERE key = 'seed_hash'").fetchone()
        if stored is None:
            self.reset()
        elif stored[0] != self._seed_hash():
            self.reload_if_changed()
        elif not self.db.execute("SELECT 1 FROM forecast_seeds LIMIT 1").fetchone():
            # Αναβάθμιση παλιάς βάσης, χωρίς απώλεια state.
            with self.db:
                self.db.executemany("INSERT INTO forecast_seeds VALUES (?, ?)",
                                    [(s["id"], json.dumps(s, ensure_ascii=False)) for s in self._seed()])

    # ---- lifecycle ----
    def _seed_hash(self) -> str:
        return hashlib.sha256(self.seed_path.read_bytes()).hexdigest()

    def _seed(self) -> list[dict]:
        return json.loads(self.seed_path.read_text(encoding="utf-8"))["suggestions"]

    @staticmethod
    def _forecast_key(s: dict) -> str:
        s = copy.deepcopy(s)
        for k in ("version", "status", "updated_at", "erp_draft_id", "VALUE", "forecast_active",
                  "forecast_update_available", "forecast_withdrawn"):
            s.pop(k, None)
        for l in s["LINES"]:
            l["QTY1"] = l.get("QTY_RECOMMENDED", l["QTY1"])
            for k in ("PRICE", "LINE_VALUE"):
                l.pop(k, None)
        s["LINES"].sort(key=lambda l: l["MTRL"])
        return json.dumps(s, sort_keys=True, ensure_ascii=False)

    def changes(self) -> dict:
        r = self.db.execute("SELECT value FROM meta WHERE key = 'forecast_changes'").fetchone()
        return json.loads(r[0]) if r else {}

    def reload_if_changed(self) -> bool:
        """Συγχρονισμός ανά πρόταση. Ποτέ reset ιστορικού ή ήδη δημιουργημένου draft."""
        raw = self.seed_path.read_bytes()
        incoming = {s["id"]: s for s in json.loads(raw)["suggestions"]}
        with self.lock, self.db:
            old = {sid: json.loads(body) for sid, body in self.db.execute("SELECT id, body FROM suggestions")}
            baseline = {sid: json.loads(body) for sid, body in self.db.execute("SELECT id, body FROM forecast_seeds")}
            delta = {"new": 0, "changed": 0, "unchanged": 0, "withdrawn": 0, "handled": 0, "at": now(), "ids": []}
            for sid, seed in incoming.items():
                prev = old.get(sid)
                different = prev is None or self._forecast_key(baseline.get(sid, prev)) != self._forecast_key(seed)
                if prev and prev.get("forecast_withdrawn"):
                    different = True
                if not different:
                    delta["unchanged"] += 1
                    continue
                terminal = prev and prev["status"] in {"draft_created", "posting", "cancelled"} and not prev.get("forecast_withdrawn")
                if terminal:
                    prev.update(forecast_update_available=True, forecast_active=True)
                    self.db.execute("UPDATE suggestions SET body = ? WHERE id = ?", (json.dumps(prev, ensure_ascii=False), sid))
                    delta["handled"] += 1
                    continue
                n = copy.deepcopy(seed)
                n.update(forecast_active=True, version=(prev["version"] + 1 if prev else seed["version"]))
                if prev:
                    # Διατηρούνται μόνο ρητές αλλαγές πωλητή που είναι ακόμη εντός των νέων ορίων.
                    edits = {l["MTRL"]: l["QTY1"] for l in prev["LINES"] if l["QTY1"] != l.get("QTY_RECOMMENDED", l["QTY1"])}
                    if prev.get("SALESMAN") == seed.get("SALESMAN"):
                        for l in n["LINES"]:
                            if l["MTRL"] in edits and l["QTY_MIN"] <= edits[l["MTRL"]] <= l["QTY_MAX"]:
                                l["QTY1"] = edits[l["MTRL"]]
                    n["status"] = "modified" if any(l["QTY1"] != l["QTY_RECOMMENDED"] for l in n["LINES"]) else "proposed"
                    self.db.execute("DELETE FROM tokens WHERE suggestion_id = ?", (sid,))
                n["updated_at"] = now()
                self.db.execute("INSERT OR REPLACE INTO suggestions VALUES (?, ?)", (sid, json.dumps(n, ensure_ascii=False)))
                delta["changed" if prev else "new"] += 1
                delta["ids"].append(sid)
                self._audit("agent", "forecast_updated" if prev else "forecast_created", sid, "νέα πρόβλεψη — απαιτείται έγκριση", snapshot=n)
            for sid, prev in old.items():
                if sid in incoming or prev.get("forecast_active") is False:
                    continue
                prev["forecast_active"] = False
                if prev["status"] not in {"draft_created", "posting", "cancelled"}:
                    prev.update(status="cancelled", forecast_withdrawn=True, version=prev["version"] + 1)
                    self.db.execute("DELETE FROM tokens WHERE suggestion_id = ?", (sid,))
                self.db.execute("UPDATE suggestions SET body = ? WHERE id = ?", (json.dumps(prev, ensure_ascii=False), sid))
                self._audit("agent", "forecast_withdrawn", sid, "Δεν υπάρχει στην τρέχουσα πρόβλεψη", snapshot=prev)
                delta["withdrawn"] += 1
            self.db.execute("DELETE FROM forecast_seeds")
            self.db.executemany("INSERT INTO forecast_seeds VALUES (?, ?)", [(sid, json.dumps(s, ensure_ascii=False)) for sid, s in incoming.items()])
            self.db.execute("INSERT OR REPLACE INTO meta VALUES ('seed_hash', ?)", (hashlib.sha256(raw).hexdigest(),))
            self.db.execute("INSERT OR REPLACE INTO meta VALUES ('forecast_changes', ?)", (json.dumps(delta),))
        return any(delta[k] for k in ("new", "changed", "withdrawn", "handled"))

    def reset(self) -> int:
        """Ξαναφορτώνει τις προτάσεις από το forecast και σβήνει state (για «Run demo scenario»)."""
        sugs = self._seed()
        with self.lock, self.db:
            for t in ("suggestions", "tokens", "idempotency", "calls", "audit", "forecast_seeds"):
                self.db.execute(f"DELETE FROM {t}")
            self.db.executemany("INSERT INTO suggestions VALUES (?, ?)",
                                [(s["id"], json.dumps(s, ensure_ascii=False)) for s in sugs])
            self.db.execute("INSERT OR REPLACE INTO meta VALUES ('seed_hash', ?)", (self._seed_hash(),))
            self.db.executemany("INSERT INTO forecast_seeds VALUES (?, ?)", [(s["id"], json.dumps(s, ensure_ascii=False)) for s in sugs])
            self.db.execute("DELETE FROM meta WHERE key = 'forecast_changes'")
            for s in sugs:
                self._audit("agent", "forecast_created", s["id"], "Πρόταση από τα δεδομένα ERP", snapshot=s)
        return len(sugs)

    # ---- suggestions ----
    def all(self) -> list[dict]:
        return [with_value(json.loads(b)) for (b,) in self.db.execute("SELECT body FROM suggestions")]

    def get(self, sid: str) -> dict | None:
        r = self.db.execute("SELECT body FROM suggestions WHERE id = ?", (sid,)).fetchone()
        return with_value(json.loads(r[0])) if r else None

    def put(self, s: dict) -> None:
        with_value(s)
        s["updated_at"] = now()
        with self.db:
            self.db.execute("UPDATE suggestions SET body = ? WHERE id = ?", (json.dumps(s, ensure_ascii=False), s["id"]))

    # ---- tokens / idempotency ----
    def new_token(self, token: str, sid: str, version: int) -> None:
        with self.db:
            self.db.execute("INSERT INTO tokens VALUES (?, ?, ?)", (token, sid, version))

    def token(self, token: str | None) -> tuple[str, int] | None:
        r = self.db.execute("SELECT suggestion_id, version FROM tokens WHERE token = ?", (token,)).fetchone()
        return (r[0], r[1]) if r else None

    def drop_tokens(self, sid: str) -> None:
        with self.db:
            self.db.execute("DELETE FROM tokens WHERE suggestion_id = ?", (sid,))

    def idem_get(self, key: str) -> dict | None:
        r = self.db.execute("SELECT response FROM idempotency WHERE key = ?", (key,)).fetchone()
        return json.loads(r[0]) if r else None

    def idem_put(self, key: str, resp: dict) -> None:
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO idempotency VALUES (?, ?)", (key, json.dumps(resp)))

    # ---- calls ----
    def calls(self) -> list[dict]:
        return [json.loads(b) for (b,) in self.db.execute("SELECT body FROM calls ORDER BY rowid DESC")]

    def call_event(self, ev: dict) -> dict:
        sid = ev["call_sid"]
        with self.lock:
            r = self.db.execute("SELECT body FROM calls WHERE call_sid = ?", (sid,)).fetchone()
            c = json.loads(r[0]) if r else {"call_sid": sid, "salesman": ev.get("salesman"), "suggestion_ids": [],
                                             "status": "queued", "started_at": now(), "ended_at": None,
                                             "transcript": [], "erp_draft_ids": []}
            if ev.get("salesman") is not None:
                c["salesman"] = ev["salesman"]
            if ev.get("status"):
                c["status"] = ev["status"]
                if ev["status"] in ("ended", "failed", "cancelled"):
                    c["ended_at"] = now()
            if ev.get("text"):
                c["transcript"].append({"role": ev.get("role") or "agent", "text": ev["text"], "at": now(),
                                        "suggestion_id": ev.get("suggestion_id"), "type": ev.get("type")})
            if ev.get("suggestion_id") and ev["suggestion_id"] not in c["suggestion_ids"]:
                c["suggestion_ids"].append(ev["suggestion_id"])
            if ev.get("erp_draft_id") and ev["erp_draft_id"] not in c["erp_draft_ids"]:
                c["erp_draft_ids"].append(ev["erp_draft_id"])
            with self.db:
                self.db.execute("INSERT OR REPLACE INTO calls VALUES (?, ?)", (sid, json.dumps(c, ensure_ascii=False)))
            return c

    # ---- audit ----
    def audit(self, actor: str, action: str, sid: str | None, outcome: str, cid: str | None = None) -> None:
        with self.lock, self.db:
            self._audit(actor, action, sid, outcome, cid, self.get(sid) if sid else None)

    def _audit(self, actor, action, sid, outcome, cid=None, snapshot=None):
        self.db.execute("INSERT INTO audit (at, actor, action, suggestion_id, outcome, correlation_id, snapshot) VALUES (?,?,?,?,?,?,?)",
                        (now(), actor, action, sid, outcome, cid, json.dumps(snapshot, ensure_ascii=False) if snapshot else None))

    def audit_log(self, limit: int = 200, sid: str | None = None) -> list[dict]:
        cols = ["at", "actor", "action", "suggestion_id", "outcome", "correlation_id"]
        where, args = (" WHERE suggestion_id = ?", (sid, limit)) if sid else ("", (limit,))
        rows = self.db.execute(f"SELECT {', '.join(cols)}, snapshot, id FROM audit{where} ORDER BY id DESC LIMIT ?", args).fetchall()
        return [{**dict(zip(cols, r[:-2])), "snapshot": json.loads(r[-2]) if r[-2] else None, "sequence": r[-1]} for r in rows]
