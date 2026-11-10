"""Campaigns (μόνο δεδομένα) και Market Scan (Claude + web search, εδώ με ψεύτικο client)."""
import json
import os
import shutil
import threading
import time
from datetime import date
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

os.environ["VR_NO_AUTOAPP"] = "1"
os.environ["AGENT_DAILY_AT"] = ""
os.environ["MARKET_SCAN_EVERY_DAYS"] = "0"
from app import explain as explain_mod  # noqa: E402
from app import market as market_mod  # noqa: E402
from app.campaigns import orthodox_easter  # noqa: E402
from app.main import _campaigns, create_app  # noqa: E402
from app.market import MarketScanner  # noqa: E402
from app.store import PROCESSED, Store  # noqa: E402


class FakeERP:
    def create_draft(self, payload):
        return 201, {"id": "DRAFT-TEST-0001", "status": "DRAFT"}


def research_reply():
    return NS(stop_reason="end_turn", usage=NS(input_tokens=1000, output_tokens=500), content=[
        NS(type="server_tool_use"),
        NS(type="web_search_tool_result", content=[NS(url="https://a.example/coffee", title="Καφές: ανατιμήσεις", page_age="1 day"),
                                                   NS(url="https://b.example/horeca", title="HoReCa 2027", page_age=None)]),
        NS(type="text", text="Ο καφές ακριβαίνει.", citations=[NS(url="https://a.example/coffee", title="Καφές: ανατιμήσεις")]),
    ])


REPORT = {"summary": "Ανεβαίνει ο καφές.",
          "price_outlook": [{"category": "Καφές", "direction": "up", "horizon": "4–8 εβδομάδες", "signal": "ανατιμήσεις",
                             "action": "Κλείσε τιμές τώρα.", "sources": [1, 99]}],
          "competitors": [], "new_products": [],
          "weaknesses": [{"title": "Χ", "our_data": "Υ", "market": "Ζ", "action": "Ω", "sources": [2]}]}


class FakeClient:
    def __init__(self, gate: threading.Event | None = None):
        self.calls, self.gate = [], gate
        self.beta = NS(messages=NS(create=self.create))

    def create(self, **kw):
        self.calls.append(kw)
        if self.gate:
            self.gate.wait(5)
        if "format" in kw.get("output_config", {}):
            return NS(stop_reason="end_turn", usage=NS(input_tokens=200, output_tokens=100),
                      content=[NS(type="text", text=json.dumps(REPORT, ensure_ascii=False))])
        return research_reply()


@pytest.fixture
def make(tmp_path, monkeypatch):
    seed = tmp_path / "suggestions.json"
    shutil.copy(PROCESSED / "suggestions.json", seed)
    monkeypatch.setattr(explain_mod, "_get_client", lambda: None)
    monkeypatch.setattr(market_mod, "SCANS_FILE", tmp_path / "market_scans.json")

    def _make(client=None, creds=True):
        scanner = MarketScanner(lambda: _campaigns().internal_snapshot(), every_days=0,
                                client_factory=lambda: client, credentials=lambda: creds)
        return TestClient(create_app(Store(tmp_path / "s.sqlite", seed), FakeERP(), market=scanner), headers={"X-Actor": "test"})
    return _make


def wait_done(c, timeout=10):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = c.get("/api/market").json()
        if not st["running"]:
            return st
        time.sleep(0.05)
    raise AssertionError("scan did not finish")


def test_orthodox_easter():
    assert [orthodox_easter(y) for y in (2024, 2025, 2026, 2027)] == [
        date(2024, 5, 5), date(2025, 4, 20), date(2026, 4, 12), date(2027, 5, 2)]


def test_campaigns_report(make):
    c = make()
    r = c.get("/api/campaigns").json()
    assert r["today"] == "2026-11-01"
    names = [e["event"] for e in r["seasonal"]]
    assert "Χριστούγεννα" in names and any(n.startswith("Πάσχα") for n in names)
    for e in r["seasonal"]:
        assert e["date"] >= r["today"] and e["past_years"]
        for it in e["items"]:
            assert it["uplift"] >= 1.25 and it["targets"]
            assert all(t["past_qty"] > 0 for t in it["targets"])
    assert {p["action"] for p in r["pricing"]} <= {"increase", "promo", "review"}
    assert r["alerts"] and all(a["items"] and a["severity"] in ("high", "medium") for a in r["alerts"])
    assert all(i["ratio"] >= 2 for a in r["alerts"] for i in a["items"])
    assert r["promos"] and r["category_response"]


def test_market_scan_without_key_reports_error(make):
    c = make(client=None, creds=False)
    assert c.get("/api/market").json()["has_credentials"] is False
    assert c.post("/api/market/scan").status_code == 202
    st = wait_done(c)
    assert st["scan"]["status"] == "error" and "ANTHROPIC_API_KEY" in st["scan"]["error"]


def test_market_scan_happy_path(make):
    fake = FakeClient()
    c = make(client=fake)
    assert c.post("/api/market/scan").status_code == 202
    st = wait_done(c)
    scan = st["scan"]
    assert scan["status"] == "done", scan.get("error")
    assert [s["url"] for s in scan["sources"]] == ["https://a.example/coffee", "https://b.example/horeca"]
    assert scan["report"]["price_outlook"][0]["sources"] == [1]          # η ανύπαρκτη πηγή 99 φεύγει
    assert scan["searches"] == 1 and scan["usage"]["input_tokens"] == 1200
    research, structure = fake.calls
    assert research["tools"][0]["type"] == "web_search_20260209"
    assert structure["output_config"]["format"]["type"] == "json_schema"
    assert "category_trend_12w_vs_last_year" in structure["messages"][0]["content"]
    assert (market_mod.SCANS_FILE).exists()


def test_market_scan_one_at_a_time(make):
    gate = threading.Event()
    c = make(client=FakeClient(gate))
    assert c.post("/api/market/scan").status_code == 202
    assert c.post("/api/market/scan").status_code == 409
    gate.set()
    assert wait_done(c)["scan"]["status"] == "done"
