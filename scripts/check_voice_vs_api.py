#!/usr/bin/env python3
"""Ελέγχει ότι ο voice agent (apps/voice/vr_core.CallSession) δουλεύει πάνω στο ΠΡΑΓΜΑΤΙΚΟ App API με τις πραγματικές προτάσεις.

Σηκώνει δικό του mock ERP (προσωρινός φάκελος drafts) και δικό του App API (προσωρινή SQLite) σε ελεύθερα ports,
οπότε ΔΕΝ πειράζει το state του demo. Τρέξε πριν το demo, μετά από κάθε αλλαγή σε api / voice / forecast:

    python3 scripts/check_voice_vs_api.py

Προϋπόθεση: έχει τρέξει το forecast (data/processed/suggestions.json), π.χ. ./scripts/dev_backend.sh μία φορά.
"""
import asyncio
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "voice"))
import vr_core as core  # noqa: E402

FAILS = []


def check(cond, msg):
    print(("  ✓ " if cond else "  ✗ ") + msg)
    if not cond:
        FAILS.append(msg)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_erp(drafts_dir):
    spec = importlib.util.spec_from_file_location("mock_erp_server", os.path.join(ROOT, "team_pack", "mock_erp_server.py"))
    erp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(erp)
    erp.DRAFTS = drafts_dir
    srv = ThreadingHTTPServer(("127.0.0.1", 0), erp.H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main():
    if not os.path.exists(os.path.join(ROOT, "data", "processed", "suggestions.json")):
        sys.exit("Λείπει το data/processed/suggestions.json — τρέξε πρώτα το forecast (./scripts/dev_backend.sh).")
    tmp = tempfile.mkdtemp(prefix="vr-check-")
    erp = start_erp(tmp)
    port = free_port()
    env = dict(os.environ, ERP_BASE_URL=f"http://127.0.0.1:{erp.server_address[1]}", API_DB=os.path.join(tmp, "state.sqlite"))
    api = subprocess.Popen(["uv", "run", "uvicorn", "app.main:app", "--port", str(port)], cwd=os.path.join(ROOT, "apps", "api"),
                           env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(base + "/api/health", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        else:
            sys.exit("Το App API δεν σηκώθηκε (uv run uvicorn στο apps/api).")
        asyncio.run(run(base, tmp))
    finally:
        api.terminate()
        erp.shutdown()
    print("\nΟΛΑ ΟΚ" if not FAILS else f"\n{len(FAILS)} ΑΠΟΤΥΧΙΕΣ")
    sys.exit(1 if FAILS else 0)


async def run(base, drafts_dir):
    def http(method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json", "X-Actor": "voice:check"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")

    async def req(m, p, b=None):
        return await asyncio.to_thread(http, m, p, b)

    async def event(**kw):
        keep = ("call_sid", "salesman", "status", "text", "role", "suggestion_id", "erp_draft_id")
        await req("POST", "/api/calls/events", {k: v for k, v in kw.items() if k in keep})

    drafts = lambda: sorted(f for f in os.listdir(drafts_dir) if f.startswith("DRAFT-"))

    print("1. Κείμενα του agent για ΟΛΕΣ τις πραγματικές προτάσεις")
    _, sugs = http("GET", "/api/suggestions")
    bad = []
    for s in sugs:
        try:
            texts = [core.explain_line(l) for l in s["LINES"]] + [core.read_back(s)]
            bad += [(s["id"], t[:60]) for t in texts if re.search(r"\d", t)]
        except Exception as e:  # noqa: BLE001
            bad.append((s["id"], repr(e)))
    check(not bad, f"{len(sugs)} προτάσεις χωρίς exception και χωρίς ψηφία στον λόγο {bad[:3] if bad else ''}")

    print("2. Ροή κλήσης σε πραγματική πρόταση")
    salesman = sugs[0]["SALESMAN"]
    sess = core.CallSession(req, salesman, "CHECK-1", on_event=event)
    open_ = await sess.load()
    s, l = open_[0], open_[0]["LINES"][0]
    check((await sess.overview())["status"] == "ok", "overview")
    check((await sess.explain(s["id"]))["status"] == "ok", "explain")
    check((await sess.change_quantity(s["id"], l["MTRL"], l["QTY_RECOMMENDED"] * 3 + 1))["status"] in ("needs_repeat", "error"),
          "πολύ μεγάλη ποσότητα → ξαναρωτά (ή εκτός ορίων)")
    check((await sess.change_quantity(s["id"], l["MTRL"], l["QTY_RECOMMENDED"] + 1))["status"] == "ok", "αλλαγή ποσότητας +1")
    check((await sess.prepare_order(s["id"]))["status"] == "awaiting_confirmation", "περίληψη πριν το write")
    check(drafts() == [], "κανένα draft πριν το «ναι»")
    p1 = await sess.place_draft_order(s["id"])
    p2 = await sess.place_draft_order(s["id"])
    check(p1["status"] == "draft_created" and p1.get("erp_draft_id") == p2.get("erp_draft_id"), "draft + επανάληψη = ίδιο id")
    check(len(drafts()) == 1, "ακριβώς ένα αρχείο draft στο ERP")
    with open(os.path.join(drafts_dir, drafts()[0]), encoding="utf-8") as f:
        sent = json.load(f)
    check(next(x["QTY1"] for x in sent["LINES"] if x["MTRL"] == l["MTRL"]) == l["QTY_RECOMMENDED"] + 1, "η αλλαγμένη ποσότητα έφτασε στο ERP")

    print("3. Ιδιοκτησία πρότασης")
    other_id = next(x for x in sugs if x["SALESMAN"] != salesman)["SALESMAN"]
    other = core.CallSession(req, other_id, "CHECK-2", on_event=event)
    await other.load()
    s2 = open_[1]
    check((await other.prepare_order(s2["id"]))["status"] == "error", "άλλος πωλητής δεν μπορεί να παραγγείλει ξένη πρόταση")

    print("4. Δύο ταυτόχρονες επιβεβαιώσεις της ίδιας πρότασης")
    a = core.CallSession(req, salesman, "CHECK-3", on_event=event)
    b = core.CallSession(req, salesman, "CHECK-4", on_event=event)
    await a.load(); await b.load()
    await a.prepare_order(s2["id"]); await b.prepare_order(s2["id"])
    ra, rb = await asyncio.gather(a.place_draft_order(s2["id"]), b.place_draft_order(s2["id"]))
    ids = {r.get("erp_draft_id") for r in (ra, rb) if r.get("erp_draft_id")}
    check(len(ids) == 1 and len(drafts()) == 2, "ένα μόνο draft για τη δεύτερη πρόταση")

    print("5. Η κλήση φαίνεται στο dashboard (/api/calls)")
    _, calls = http("GET", "/api/calls")
    c1 = next((c for c in calls if c["call_sid"] == "CHECK-1"), None)
    check(c1 is not None and c1["status"] == "draft_created" and c1["erp_draft_ids"], "status + draft id στο /api/calls")


if __name__ == "__main__":
    main()
