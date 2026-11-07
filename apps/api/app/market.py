"""Market Scan: εβδομαδιαία έρευνα αγοράς με Claude + web search, διασταυρωμένη με τα δικά μας δεδομένα.

Δύο βήματα:
1. Έρευνα: το Claude ψάχνει στο internet (web search) τάσεις τιμών, κινήσεις ανταγωνιστών και νέα προϊόντα
   για χονδρεμπόριο ποτών/τροφίμων/αναλωσίμων HoReCa στην Ελλάδα. Κάθε εύρημα κρατά τις πηγές του.
2. Δομή: τα ευρήματα + μια σύνοψη από ΤΑ ΔΙΚΑ ΜΑΣ δεδομένα (Campaigns.internal_snapshot) → JSON με
   τάσεις τιμών, ανταγωνιστές, νέα προϊόντα, αδυναμίες μας, και μια ενέργεια για καθένα.

Κανόνας: αριθμοί μόνο από τις πηγές ή από τα εσωτερικά δεδομένα — το LLM δεν βγάζει δικούς του.
Χρονοπρογραμματισμός: MARKET_SCAN_EVERY_DAYS (default 7, 0 = κλειστό)· κουμπί «Σκάναρε τώρα» στο dashboard.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import anthropic

from .explain import _get_client
from .store import PROCESSED

log = logging.getLogger("market")
MODEL = os.environ.get("MARKET_MODEL", "claude-opus-5-5")
SCANS_FILE = PROCESSED / "market_scans.json"
KEEP = 12
MAX_SEARCHES = 15
FALLBACK = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}

RESEARCH_SYSTEM = """Είσαι αναλυτής αγοράς για την DEMO ΔΙΑΝΟΜΕΣ Α.Ε., χονδρέμπορο στην Ελλάδα που διανέμει νερά, αναψυκτικά,
μπύρες, καφέ, σνακ, παγωτά, χαρτικά, αναλώσιμα και απορρυπαντικά σε ξενοδοχεία, εστιατόρια, καφετέριες, μπαρ και mini markets.
Κάνε έρευνα στο internet για την ελληνική αγορά (και την ευρωπαϊκή όπου επηρεάζει την ελληνική) για τις επόμενες 4–12 εβδομάδες:
1. Τάσεις τιμών ανά κατηγορία: ανατιμήσεις παραγωγών, κόστος πρώτων υλών (π.χ. καφές, ζάχαρη, αλουμίνιο, PET, χαρτί),
   ενέργεια, μεταφορικά, πληθωρισμός τροφίμων, φόροι/τέλη.
2. Ανταγωνιστές: χονδρέμποροι και cash & carry που εξυπηρετούν HoReCa στην Ελλάδα — προσφορές, νέα κανάλια, εξαγορές, επεκτάσεις.
3. Νέα προϊόντα και τάσεις κατανάλωσης στο HoReCa και στα mini markets (π.χ. χωρίς ζάχαρη, χωρίς αλκοόλ, functional, eco συσκευασίες).
4. Ό,τι αλλάζει τη ζήτηση: τουρισμός (κρατήσεις, σεζόν), εκδηλώσεις, νομοθεσία (π.χ. πλαστικά μιας χρήσης).
Γράψε στα ελληνικά, σύντομα, με το εύρημα και από πού προέρχεται. Μόνο ό,τι βρήκες σε πηγές — αν κάτι δεν βρέθηκε, πες το.
Μην επινοείς ποσοστά ή τιμές."""

STRUCTURE_SYSTEM = """Μετατρέπεις μια έρευνα αγοράς σε αναφορά για το dashboard της DEMO ΔΙΑΝΟΜΕΣ.
Θα πάρεις: (α) τα ευρήματα της έρευνας, (β) αριθμημένη λίστα πηγών, (γ) σύνοψη από τα δικά μας δεδομένα πωλήσεων.
Κανόνες:
- Ελληνικά, σύντομες προτάσεις, πρακτικές ενέργειες για τον διευθυντή πωλήσεων ή τον πωλητή.
- Κάθε στοιχείο αγοράς έχει `sources` με τους αριθμούς των πηγών που το στηρίζουν. Χωρίς πηγή → μην το βάλεις.
- Αριθμούς (ποσοστά, τιμές) γράφεις ΜΟΝΟ αν υπάρχουν αυτούσιοι στα ευρήματα/πηγές ή στα δικά μας δεδομένα.
- Στο `weaknesses` διασταύρωσε την αγορά με τα δικά μας δεδομένα: π.χ. κατηγορία που πέφτει σε εμάς ενώ η αγορά ανεβαίνει,
  είδη που φεύγουν από πελάτες (σπασμένος κύκλος) ενώ ανταγωνιστής κάνει προσφορές, νέα τάση που δεν καλύπτει ο κατάλογός μας.
  Το `our_data` περιγράφει τι δείχνουν ΤΑ ΔΙΚΑ ΜΑΣ δεδομένα (με τους αριθμούς τους).
- `direction`: up = ανεβαίνουν οι τιμές, down = πέφτουν, stable = σταθερές, mixed = αντικρουόμενα σήματα."""

_SRC = {"type": "array", "items": {"type": "integer"}}
_ACTION = {"type": "string", "description": "Τι να κάνουμε, σε μία πρόταση"}
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["summary", "price_outlook", "competitors", "new_products", "weaknesses"],
    "properties": {
        "summary": {"type": "string", "description": "3–4 προτάσεις: τι αλλάζει στην αγορά και τι σημαίνει για εμάς"},
        "price_outlook": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["category", "direction", "horizon", "signal", "action", "sources"],
            "properties": {"category": {"type": "string"}, "direction": {"type": "string", "enum": ["up", "down", "stable", "mixed"]},
                           "horizon": {"type": "string"}, "signal": {"type": "string"}, "action": _ACTION, "sources": _SRC}}},
        "competitors": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["name", "move", "impact", "action", "sources"],
            "properties": {"name": {"type": "string"}, "move": {"type": "string"}, "impact": {"type": "string"},
                           "action": _ACTION, "sources": _SRC}}},
        "new_products": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["product", "trend", "fit", "action", "sources"],
            "properties": {"product": {"type": "string"}, "trend": {"type": "string"},
                           "fit": {"type": "string", "description": "Για ποιους πελάτες μας (τύπος/περιοχή) και αν το έχουμε στον κατάλογο"},
                           "action": _ACTION, "sources": _SRC}}},
        "weaknesses": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["title", "our_data", "market", "action", "sources"],
            "properties": {"title": {"type": "string"}, "our_data": {"type": "string"}, "market": {"type": "string"},
                           "action": _ACTION, "sources": _SRC}}},
    },
}


def has_credentials() -> bool:
    """Το SDK φτιάχνει client και χωρίς κλειδί (αποτυγχάνει στο αίτημα) — ελέγχουμε τις πηγές credentials."""
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                or os.environ.get("ANTHROPIC_PROFILE") or (Path.home() / ".config" / "anthropic").is_dir())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class MarketScanner:
    def __init__(self, snapshot: Callable[[], dict], every_days: int | None = None, client_factory=_get_client,
                 credentials: Callable[[], bool] = has_credentials):
        self.snapshot = snapshot
        self.client_factory = client_factory
        self.credentials = credentials
        self.every_days = int(os.environ.get("MARKET_SCAN_EVERY_DAYS", "7") or 0) if every_days is None else every_days
        self.lock = threading.Lock()
        self.current: dict | None = None
        self.scans: list[dict] = self._load()
        if self.every_days > 0:
            threading.Thread(target=self._scheduler, daemon=True).start()

    # ---------- αποθήκευση ----------
    def _load(self) -> list[dict]:
        try:
            return json.loads(SCANS_FILE.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save(self) -> None:
        SCANS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = SCANS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.scans[:KEEP], ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(SCANS_FILE)

    # ---------- κατάσταση για το dashboard ----------
    def _last_ok(self) -> dict | None:
        return next((s for s in self.scans if s.get("status") == "done"), None)

    def next_run_at(self) -> str | None:
        if self.every_days <= 0:
            return None
        last = self._last_ok()
        if not last:
            return _now()
        t = datetime.fromisoformat(last["started_at"].replace("Z", "+00:00")) + timedelta(days=self.every_days)
        return t.isoformat(timespec="seconds").replace("+00:00", "Z")

    def state(self, scan_id: str | None = None) -> dict:
        with self.lock:
            chosen = next((s for s in self.scans if s["id"] == scan_id), None) if scan_id else (self._last_ok() or
                                                                                                  (self.scans[0] if self.scans else None))
            return {"running": self.current is not None, "current": self.current,
                    "has_credentials": self.credentials(), "model": MODEL,
                    "every_days": self.every_days, "next_run_at": self.next_run_at(),
                    "scan": chosen,
                    "history": [{k: s.get(k) for k in ("id", "trigger", "started_at", "finished_at", "status", "error")}
                                for s in self.scans]}

    # ---------- εκτέλεση ----------
    def start(self, trigger: str = "manual") -> dict | None:
        with self.lock:
            if self.current is not None:
                return None
            self.current = {"id": f"MS-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}", "trigger": trigger,
                            "started_at": _now(), "status": "running", "step": "Ξεκινά…"}
            run = dict(self.current)
        threading.Thread(target=self._run, args=(run,), daemon=True).start()
        return run

    def _step(self, text: str) -> None:
        with self.lock:
            if self.current:
                self.current["step"] = text

    def _run(self, run: dict) -> None:
        try:
            client = self.client_factory() if self.credentials() else None
            if client is None:
                raise RuntimeError("Δεν υπάρχει κλειδί Anthropic: βάλε ANTHROPIC_API_KEY στο .env και ξεκίνα ξανά το backend.")
            self._step("Σύνοψη των δικών μας δεδομένων…")
            internal = self.snapshot()
            self._step("Έρευνα στο internet (τιμές, ανταγωνιστές, νέα προϊόντα)…")
            notes, sources, searches, usage = self._research(client)
            self._step(f"Διασταύρωση {len(sources)} πηγών με τα δεδομένα μας…")
            report, u2 = self._structure(client, notes, sources, internal)
            n = len(sources)
            for sec in ("price_outlook", "competitors", "new_products", "weaknesses"):   # μόνο υπαρκτές πηγές
                for row in report.get(sec, []):
                    row["sources"] = sorted({i for i in row.get("sources", []) if 1 <= i <= n})
            run.update(status="done", report=report, notes=notes, searches=searches,
                       sources=[{"i": i + 1, **s} for i, s in enumerate(sources)],
                       internal=internal, usage={k: usage.get(k, 0) + u2.get(k, 0) for k in ("input_tokens", "output_tokens")})
        except Exception as e:                                   # το dashboard δείχνει το λάθος· ο server συνεχίζει
            log.exception("market scan failed")
            run.update(status="error", error=_friendly(e))
        run["finished_at"] = _now()
        run.pop("step", None)
        with self.lock:
            self.scans.insert(0, run)
            self.scans = self.scans[:KEEP]
            self.current = None
            self._save()

    def _research(self, client: anthropic.Anthropic) -> tuple[str, list[dict], int, dict]:
        today = datetime.now().strftime("%d/%m/%Y")
        messages = [{"role": "user", "content": f"Σήμερα είναι {today}. Κάνε την εβδομαδιαία έρευνα αγοράς."}]
        tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": MAX_SEARCHES,
                  "user_location": {"type": "approximate", "country": "GR", "city": "Athens", "timezone": "Europe/Athens"}}]
        texts, sources, seen, searches, usage = [], [], {}, 0, {"input_tokens": 0, "output_tokens": 0}
        for _ in range(4):                                       # pause_turn → συνέχεια, ως 4 γύροι
            r = client.beta.messages.create(model=MODEL, max_tokens=16000, system=RESEARCH_SYSTEM, tools=tools,
                                            messages=messages, output_config={"effort": "medium"}, **FALLBACK)
            usage["input_tokens"] += r.usage.input_tokens
            usage["output_tokens"] += r.usage.output_tokens
            if r.stop_reason == "refusal":
                raise RuntimeError("Το μοντέλο αρνήθηκε την έρευνα.")
            for b in r.content:
                if b.type == "server_tool_use":
                    searches += 1
                elif b.type == "web_search_tool_result" and isinstance(b.content, list):
                    for res in b.content:
                        _add(sources, seen, getattr(res, "url", None), getattr(res, "title", None), getattr(res, "page_age", None))
                elif b.type == "text":
                    texts.append(b.text)
                    for c in getattr(b, "citations", None) or []:
                        _add(sources, seen, getattr(c, "url", None), getattr(c, "title", None), None)
            if r.stop_reason != "pause_turn":
                break
            messages.append({"role": "assistant", "content": r.content})
        notes = "".join(texts).strip()
        if not notes:
            raise RuntimeError("Η έρευνα δεν επέστρεψε ευρήματα.")
        return notes, sources, searches, usage

    def _structure(self, client: anthropic.Anthropic, notes: str, sources: list[dict], internal: dict) -> tuple[dict, dict]:
        src = "\n".join(f"[{i + 1}] {s['title'] or s['url']} — {s['url']}" for i, s in enumerate(sources)) or "(καμία)"
        content = (f"ΕΥΡΗΜΑΤΑ ΕΡΕΥΝΑΣ:\n{notes}\n\nΠΗΓΕΣ:\n{src}\n\n"
                   f"ΤΑ ΔΙΚΑ ΜΑΣ ΔΕΔΟΜΕΝΑ (ως {internal.get('data_until')}):\n{json.dumps(internal, ensure_ascii=False)}")
        r = client.beta.messages.create(
            model=MODEL, max_tokens=16000, system=STRUCTURE_SYSTEM, messages=[{"role": "user", "content": content}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}}, **FALLBACK)
        if r.stop_reason == "refusal":
            raise RuntimeError("Το μοντέλο αρνήθηκε τη σύνοψη.")
        if r.stop_reason == "max_tokens":
            raise RuntimeError("Η αναφορά κόπηκε (max_tokens).")
        text = next(b.text for b in r.content if b.type == "text")
        return json.loads(text), {"input_tokens": r.usage.input_tokens, "output_tokens": r.usage.output_tokens}

    # ---------- εβδομαδιαίο ----------
    def _scheduler(self) -> None:
        time.sleep(300)                                          # όχι πάνω στην εκκίνηση/στα tests
        while True:
            try:
                nxt = self.next_run_at()
                due = nxt and datetime.fromisoformat(nxt.replace("Z", "+00:00")) <= datetime.now(timezone.utc)
                if due and self.credentials():
                    self.start("schedule")
            except Exception:
                log.exception("market scheduler")
            time.sleep(3600)


def _add(sources: list[dict], seen: dict, url: str | None, title: str | None, page_age: str | None) -> None:
    if url and url not in seen:
        seen[url] = len(sources)
        sources.append({"url": url, "title": title or url, "page_age": page_age})


def _friendly(e: Exception) -> str:
    if isinstance(e, anthropic.AuthenticationError):
        return "Το κλειδί Anthropic δεν έγινε δεκτό (ANTHROPIC_API_KEY)."
    if isinstance(e, anthropic.RateLimitError):
        return "Όριο χρήσης του Anthropic API — δοκίμασε σε λίγο."
    if isinstance(e, anthropic.APIConnectionError):
        return "Δεν υπάρχει σύνδεση με το Anthropic API."
    if isinstance(e, anthropic.APIStatusError):
        return f"Anthropic API: HTTP {e.status_code}"
    return str(e)
