"""State σε SQLite: suggestions (JSON), confirmation tokens, idempotency, calls, audit.

Όλες οι αλλαγές περνάνε από εδώ με ένα lock — μία διεργασία uvicorn είναι αρκετή για το demo.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
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
"""


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Store:
    def __init__(self, db_path: Path = DB_PATH, seed_path: Path = PROCESSED / "suggestions.json"):
        self.lock = threading.RLock()
        self.seed_path = seed_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.executescript(SCHEMA)
        # Νέο τρέξιμο του forecast (άλλο suggestions.json) → οι παλιές προτάσεις δεν ισχύουν πια.
        stored = self.db.execute("SELECT value FROM meta WHERE key = 'seed_hash'").fetchone()
        if stored is None or stored[0] != self._seed_hash():
            if stored is not None:
                logging.getLogger("store").info("suggestions.json changed → reloading proposals")
            self.reset()

    # ---- lifecycle ----
    def _seed_hash(self) -> str:
        return hashlib.sha256(self.seed_path.read_bytes()).hexdigest()

    def reset(self) -> int:
        """Ξαναφορτώνει τις προτάσεις από το forecast και σβήνει state (για «Run demo scenario»)."""
        sugs = json.loads(self.seed_path.read_text(encoding="utf-8"))["suggestions"]
        with self.lock, self.db:
            for t in ("suggestions", "tokens", "idempotency", "calls", "audit"):
                self.db.execute(f"DELETE FROM {t}")
            self.db.executemany("INSERT INTO suggestions VALUES (?, ?)",
                                [(s["id"], json.dumps(s, ensure_ascii=False)) for s in sugs])
            self.db.execute("INSERT OR REPLACE INTO meta VALUES ('seed_hash', ?)", (self._seed_hash(),))
        return len(sugs)

    # ---- suggestions ----
    def all(self) -> list[dict]:
        return [json.loads(b) for (b,) in self.db.execute("SELECT body FROM suggestions")]

    def get(self, sid: str) -> dict | None:
        r = self.db.execute("SELECT body FROM suggestions WHERE id = ?", (sid,)).fetchone()
        return json.loads(r[0]) if r else None

    def put(self, s: dict) -> None:
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
                c["transcript"].append({"role": ev.get("role") or "agent", "text": ev["text"], "at": now()})
            if ev.get("suggestion_id") and ev["suggestion_id"] not in c["suggestion_ids"]:
                c["suggestion_ids"].append(ev["suggestion_id"])
            if ev.get("erp_draft_id") and ev["erp_draft_id"] not in c["erp_draft_ids"]:
                c["erp_draft_ids"].append(ev["erp_draft_id"])
            with self.db:
                self.db.execute("INSERT OR REPLACE INTO calls VALUES (?, ?)", (sid, json.dumps(c, ensure_ascii=False)))
            return c

    # ---- audit ----
    def audit(self, actor: str, action: str, sid: str | None, outcome: str, cid: str | None = None) -> None:
        with self.db:
            self.db.execute("INSERT INTO audit (at, actor, action, suggestion_id, outcome, correlation_id) VALUES (?,?,?,?,?,?)",
                            (now(), actor, action, sid, outcome, cid))

    def audit_log(self, limit: int = 200) -> list[dict]:
        cols = ["at", "actor", "action", "suggestion_id", "outcome", "correlation_id"]
        rows = self.db.execute(f"SELECT {', '.join(cols)} FROM audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(zip(cols, r)) for r in rows]
