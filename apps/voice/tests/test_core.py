"""Tests του vr_core πάνω στους ΠΡΑΓΜΑΤΙΚΟΥΣ mock servers (ERP + App API), μέσα στο ίδιο process.

    python3 -m unittest discover -s apps/voice/tests -v

Μόνο standard library — τρέχει και με το python3.9 του Mac.
"""
import asyncio
import copy
import importlib.util
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.dirname(HERE))
import vr_core as core  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _serve(handler):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class Words(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(core.num_words(4), "τέσσερα")
        self.assertEqual(core.num_words(15), "δεκαπέντε")
        self.assertEqual(core.num_words(50), "πενήντα")
        self.assertEqual(core.num_words(21), "είκοσι ένα")
        self.assertEqual(core.num_words(100), "εκατό")
        self.assertEqual(core.num_words(101), "εκατόν ένα")
        self.assertEqual(core.num_words(250), "διακόσια πενήντα")
        self.assertEqual(core.num_words(24, feminine=True), "είκοσι τέσσερις")
        self.assertEqual(core.num_words(13, feminine=True), "δεκατρείς")

    def test_qty_and_dates(self):
        self.assertEqual(core.qty_words(1, "ΚΙΒ"), "ένα κιβώτιο")
        self.assertEqual(core.qty_words(4, "ΚΙΒ"), "τέσσερα κιβώτια")
        self.assertEqual(core.qty_words(3, "ΤΕΜ"), "τρία τεμάχια")
        self.assertEqual(core.spoken_date("2026-11-03"), "την Τρίτη τρεις Νοεμβρίου")
        self.assertEqual(core.spoken_day_month("2026-11-01"), "πρώτη Νοεμβρίου")
        self.assertEqual(core.spoken_date("2026-11-07"), "το Σάββατο επτά Νοεμβρίου")
        self.assertEqual(core.spoken_digits("0012"), "μηδέν μηδέν ένα δύο")

    def test_names(self):
        self.assertEqual(core.spoken_item("Νερό 0,5L κιβ. 24τεμ"), "Νερό μισό λίτρο")
        self.assertEqual(core.spoken_item("Ice tea λεμόνι 500ml κιβ. 12τεμ"), "Ice tea λεμόνι πεντακόσια ml")
        self.assertEqual(core.spoken_customer("Mini Market Οικονομικό Μ.Ε.Π.Ε."), "Mini Market Οικονομικό")
        self.assertEqual(core.spoken_customer("Ταβέρνα Η Αυλή Α.Ε."), "Ταβέρνα Η Αυλή")

    def test_no_digits_in_spoken_text(self):
        with open(os.path.join(ROOT, "fixtures", "suggestions.sample.json"), encoding="utf-8") as f:
            fixture = json.load(f)
        for s in fixture["suggestions"]:
            for text in [core.suggestion_brief(s), core.read_back(s)] + [core.explain_line(l) for l in s["LINES"]]:
                self.assertNotRegex(text, r"\d", text)


class Flow(unittest.TestCase):
    """Ολόκληρη η ροή κλήσης πάνω στους πραγματικούς mock servers."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="vr-drafts-")
        cls.erp = _load("mock_erp_server", os.path.join(ROOT, "team_pack", "mock_erp_server.py"))
        cls.erp.DRAFTS = cls.tmp                                   # τα drafts του test όχι στο team_pack/
        orig_post = cls.erp.H.do_POST

        def slow_post(self):                                        # αργό ERP → ορατό race στο create-draft
            time.sleep(0.3)
            return orig_post(self)
        cls.erp.H.do_POST = slow_post
        cls.erp_srv = _serve(cls.erp.H)
        os.environ["ERP_BASE_URL"] = f"http://127.0.0.1:{cls.erp_srv.server_address[1]}"
        cls.api = _load("mock_app_api", os.path.join(ROOT, "scripts", "mock_app_api.py"))
        cls.api_srv = _serve(cls.api.H)
        cls.base = f"http://127.0.0.1:{cls.api_srv.server_address[1]}"
        cls.fixture = {s["id"]: s for s in json.load(open(cls.api.FIXTURE, encoding="utf-8"))["suggestions"]}

    @classmethod
    def tearDownClass(cls):
        cls.api_srv.shutdown(); cls.erp_srv.shutdown()

    def setUp(self):
        self.api.SUGS.clear(); self.api.SUGS.update(copy.deepcopy(self.fixture))
        self.api.TOKENS.clear(); self.api.IDEMP.clear(); self.api.CALLS.clear()
        for f in os.listdir(self.tmp):
            os.remove(os.path.join(self.tmp, f))
        self.sug = next(iter(self.fixture.values()))
        self.events = []

    # ---- HTTP προς τον mock App API ----
    def _http(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json", "X-Actor": "voice:test"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")

    async def _req(self, method, path, body=None):
        return await asyncio.to_thread(self._http, method, path, body)

    async def _event(self, **kw):
        self.events.append(kw)

    def session(self, salesman=None):
        return core.CallSession(self._req, salesman or self.sug["SALESMAN"], "CALLTEST", on_event=self._event)

    def drafts(self):
        return sorted(os.listdir(self.tmp))

    def run_(self, coro):
        return asyncio.run(coro)

    # ---- tests ----
    def test_happy_path_exactly_one_draft(self):
        async def go():
            s = self.session()
            ov = await s.overview()
            self.assertGreater(ov["count"], 0)
            sid, line = self.sug["id"], self.sug["LINES"][0]
            ex = await s.explain(sid)
            self.assertEqual(ex["status"], "ok")
            new_qty = line["QTY_RECOMMENDED"] + 1
            r = await s.change_quantity(sid, line["MTRL"], new_qty)
            self.assertEqual(r["status"], "ok", r)
            r = await s.place_draft_order(sid)                      # χωρίς περίληψη → όχι
            self.assertEqual(r["status"], "error")
            self.assertEqual(self.drafts(), [])
            r = await s.prepare_order(sid)
            self.assertEqual(r["status"], "awaiting_confirmation")
            self.assertIn(core.qty_words(new_qty, line["UNIT"]), r["say"])
            r = await s.place_draft_order(sid)
            self.assertEqual(r["status"], "draft_created", r)
            again = await s.place_draft_order(sid)                  # διπλό «ναι»
            self.assertEqual(again["erp_draft_id"], r["erp_draft_id"])
            return r["erp_draft_id"]
        did = self.run_(go())
        self.assertEqual(self.drafts(), [did + ".json"])
        body = json.load(open(os.path.join(self.tmp, did + ".json"), encoding="utf-8"))
        self.assertEqual(body["TRDR"], self.sug["TRDR"])
        self.assertEqual(body["LINES"][0]["QTY1"], self.sug["LINES"][0]["QTY_RECOMMENDED"] + 1)
        self.assertIn("draft_created", [e.get("status") for e in self.events])

    def test_change_after_readback_blocks_write(self):
        async def go():
            s = self.session()
            sid, line = self.sug["id"], self.sug["LINES"][0]
            await s.prepare_order(sid)
            await s.change_quantity(sid, line["MTRL"], line["QTY_RECOMMENDED"] + 1)
            return await s.place_draft_order(sid)
        r = self.run_(go())
        self.assertEqual(r["status"], "error")
        self.assertEqual(self.drafts(), [])

    def test_large_quantity_needs_repeat_and_bounds(self):
        async def go():
            s = self.session()
            sid, line = self.sug["id"], self.sug["LINES"][0]
            big = min(line["QTY_MAX"], 2 * line["QTY_RECOMMENDED"] + 1)
            r1 = await s.change_quantity(sid, line["MTRL"], big)
            r2 = await s.change_quantity(sid, line["MTRL"], big, large_confirmed=True)
            r3 = await s.change_quantity(sid, line["MTRL"], line["QTY_MAX"] + 1, large_confirmed=True)
            r4 = await s.change_quantity(sid, 999999, 1)
            return big, r1, r2, r3, r4
        big, r1, r2, r3, r4 = self.run_(go())
        if big > 2 * self.sug["LINES"][0]["QTY_RECOMMENDED"]:
            self.assertEqual(r1["status"], "needs_repeat")
        self.assertEqual(r2["status"], "ok", r2)
        self.assertEqual(r3["status"], "error")
        self.assertEqual(r4["status"], "error")

    def test_other_salesman_cannot_touch(self):
        other = next(s for s in self.fixture.values() if s["SALESMAN"] != self.sug["SALESMAN"])
        async def go():
            s = self.session()
            return (await s.prepare_order(other["id"]),
                    await s.change_quantity(other["id"], other["LINES"][0]["MTRL"], 1))
        r1, r2 = self.run_(go())
        self.assertEqual(r1["status"], "error")
        self.assertEqual(r2["status"], "error")

    def test_mock_api_concurrent_create_draft_writes_once(self):
        """Διπλό webhook/retry: δύο create-draft ταυτόχρονα → ΕΝΑ draft στο ERP."""
        sid = self.sug["id"]
        code, conf = self._http("POST", f"/api/suggestions/{sid}/confirm", {"version": self.sug["version"]})
        self.assertEqual(code, 200)
        results = []
        def hit(key):
            results.append(self._http("POST", f"/api/suggestions/{sid}/create-draft",
                                      {"confirmation_token": conf["confirmation_token"], "idempotency_key": key}))
        ts = [threading.Thread(target=hit, args=(k,)) for k in ("a", "b", "a")]
        for t in ts: t.start()
        for t in ts: t.join()
        self.assertEqual(len(self.drafts()), 1, results)
        ok = [r for c, r in results if c == 200]
        self.assertTrue(ok)
        self.assertEqual({r["erp_draft_id"] for r in ok}, {self.drafts()[0][:-5]})

    def test_mock_api_salesmen_and_days_left(self):
        code, sm = self._http("GET", "/api/salesmen")
        self.assertEqual(code, 200)
        self.assertEqual(len(sm), 5)
        code, risk = self._http("GET", "/api/risk")
        self.assertTrue(all("days_left" in r for r in risk))


if __name__ == "__main__":
    unittest.main()
