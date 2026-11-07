"""Εκτέλεση του VORA agent (services/forecast/src/forecast/agent.py) από το App API.

Ο agent τρέχει ως ξεχωριστή διεργασία (ίδιο περιβάλλον με το forecast) και γράφει γεγονότα σε JSON lines·
εδώ τα μαζεύουμε σε μία εγγραφή που ρωτάει το dashboard (GET /api/agent) όσο τρέχει.
Στο τέλος: αν άλλαξαν οι προτάσεις, το store τις ξαναφορτώνει (αλλιώς οι εγκρίσεις μένουν ως έχουν).

Χρονοπρογραμματισμός: AGENT_DAILY_AT="06:00" (default) → μία εκτέλεση τη μέρα. Κενό = κλειστό.
"""
from __future__ import annotations

import json
import logging
import os
import shlex
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

from .store import PROCESSED, ROOT

FORECAST_DIR = ROOT / "services" / "forecast"
RUNS_FILE = PROCESSED / "agent_runs.json"
HANDOFF = ("handoff", "Παράδοση στον πωλητή")
log = logging.getLogger("agent")


def default_cmd(trigger: str) -> list[str]:
    if os.environ.get("AGENT_CMD"):
        return shlex.split(os.environ["AGENT_CMD"]) + ["--trigger", trigger]
    erp = os.environ.get("ERP_BASE_URL", "http://localhost:8080")
    return ["uv", "run", "--project", str(FORECAST_DIR), "python", "-m", "forecast.agent", "--jsonl", "--erp", erp, "--trigger", trigger]


def shape(rec: dict) -> dict:
    """Εγγραφή του αρχείου runs (steps = λίστα) → ίδια μορφή με τη live (steps = dict ανά βήμα)."""
    if isinstance(rec.get("steps"), dict):
        return rec
    steps = {s["key"]: {k: s.get(k) for k in ("status", "detail", "metrics", "ms")} for s in rec.get("steps", [])}
    plan = rec.get("plan") or [{"key": s["key"], "label": s["label"]} for s in rec.get("steps", [])]
    return {**rec, "steps": steps, "plan": plan, "progress": {}, "warnings": rec.get("warnings", [])}


class AgentRunner:
    def __init__(self, on_finish: Callable[[dict], dict], cmd: Callable[[str], list[str]] = default_cmd,
                 runs_file: Path = RUNS_FILE, schedule: str | None = None):
        self.on_finish, self.cmd, self.runs_file = on_finish, cmd, runs_file
        self.lock = threading.Lock()
        self.current: dict | None = None
        self.last_extra: dict[str, dict] = {}            # πληροφορίες του API (reload) ανά run id
        self.schedule = os.environ.get("AGENT_DAILY_AT", "06:00") if schedule is None else schedule
        if self.schedule:
            threading.Thread(target=self._scheduler, daemon=True).start()

    # ---- δημόσια ----
    def start(self, trigger: str = "manual") -> dict | None:
        with self.lock:
            if self.current and self.current["status"] == "running":
                return None
            self.current = {"id": None, "trigger": trigger, "status": "running", "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "source": None, "plan": [], "steps": {}, "progress": {}, "warnings": []}
        threading.Thread(target=self._run, args=(self.current,), daemon=True).start()
        return self.current

    def state(self) -> dict:
        runs = [shape(r) for r in self._runs()]
        for r in runs:
            r.update(self.last_extra.get(r.get("id"), {}))
        cur = self.current if self.current and self.current["status"] == "running" else None
        last = self.current if self.current and self.current["status"] != "running" else (runs[0] if runs else None)
        return {"running": cur is not None, "current": cur, "last": last, "schedule": self.schedule or None,
                "runs": [{k: r.get(k) for k in ("id", "trigger", "status", "started_at", "finished_at", "source", "summary")} for r in runs[:10]]}

    # ---- εσωτερικά ----
    def _runs(self) -> list[dict]:
        try:
            return json.loads(self.runs_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []

    def _run(self, live: dict) -> None:
        try:
            p = subprocess.Popen(self.cmd(live["trigger"]), cwd=FORECAST_DIR, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, encoding="utf-8")
            for line in p.stdout:
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                self._apply(live, ev)
            err = p.stderr.read()
            code = p.wait()
            if code != 0 and live.get("agent_status") != "error":
                live["agent_status"] = "error"
                live["warnings"].append((err.strip().splitlines() or [f"exit {code}"])[-1])
        except OSError as e:
            live["agent_status"] = "error"; live["warnings"].append(f"ο agent δεν ξεκίνησε: {e}")
        t0 = time.time()
        final = live.get("agent_status") or "error"
        if final == "done":
            try:
                extra = self.on_finish(live) or {}
                live["steps"][HANDOFF[0]] = {"status": "done", "detail": extra.get("detail"), "metrics": extra, "ms": int((time.time() - t0) * 1000)}
            except Exception as e:  # noqa: BLE001
                live["steps"][HANDOFF[0]] = {"status": "error", "detail": str(e), "ms": 0}
                final = "error"
        if live.get("id"):
            self.last_extra[live["id"]] = {"steps": live["steps"], "plan": live["plan"], "status": final}
        live.setdefault("finished_at", time.strftime("%Y-%m-%dT%H:%M:%S"))
        live["status"] = final        # τελευταίο: ως τότε το dashboard βλέπει «τρέχει»

    @staticmethod
    def _apply(live: dict, ev: dict) -> None:
        t = ev.get("type")
        if t == "run":
            live.update({k: ev.get(k) for k in ("id", "started_at", "source")})
            live["plan"] = ev.get("plan", []) + [{"key": HANDOFF[0], "label": HANDOFF[1]}]
        elif t == "step":
            live["steps"][ev["key"]] = {k: ev.get(k) for k in ("status", "detail", "metrics", "ms")}
        elif t == "progress":
            live["progress"][ev["key"]] = {k: ev.get(k) for k in ("detail", "done", "total")}
        elif t == "warning":
            live["warnings"].append(ev.get("detail"))
            if ev.get("key") == "fetch":
                live["source"] = "csv"
        elif t == "end":
            live["agent_status"] = ev.get("status", "error"); live["finished_at"] = ev.get("finished_at")

    def _scheduler(self) -> None:
        done_on = None
        while True:
            now = time.localtime()
            if time.strftime("%H:%M", now) == self.schedule and done_on != now.tm_yday:
                done_on = now.tm_yday
                log.info("scheduled agent run")
                self.start("schedule")
            time.sleep(20)
