"""Αλλαγές τιμών από τον χρήστη + SMS προσφοράς (κείμενο AI με φύλακα αριθμών, Apifon με HMAC, ένα πάτημα = ένα SMS)."""
import base64
import hashlib
import hmac
import json
import os
import shutil
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

os.environ["VR_NO_AUTOAPP"] = "1"
os.environ["AGENT_DAILY_AT"] = ""
os.environ["MARKET_SCAN_EVERY_DAYS"] = "0"
from app import explain as explain_mod  # noqa: E402
from app import outreach  # noqa: E402
from app.main import create_app  # noqa: E402
from app.market import MarketScanner  # noqa: E402
from app.store import PROCESSED, Store  # noqa: E402


class FakeERP:
    def create_draft(self, payload):
        return 201, {"id": "DRAFT-TEST-0001", "status": "DRAFT"}


class FakeHTTP:
    def __init__(self, status=200, body=None):
        self.calls, self.status, self.body = [], status, body

    def __call__(self, url, content, headers):
        self.calls.append({"url": url, "content": content, "headers": headers})
        number = json.loads(content)["subscribers"][0]["number"]
        body = self.body or {"request_id": "req-1", "results": {number: [{"message_id": f"msg-{len(self.calls)}"}]},
                             "result_info": {"status_code": "200", "description": "OK"}}
        return NS(status_code=self.status, json=lambda: body)


@pytest.fixture
def env(tmp_path, monkeypatch):
    seed = tmp_path / "suggestions.json"
    shutil.copy(PROCESSED / "suggestions.json", seed)
    monkeypatch.setattr(explain_mod, "_get_client", lambda: None)
    monkeypatch.setattr(outreach, "has_credentials", lambda: False)
    monkeypatch.setenv("SMS_DEMO_TO", "+30 694 715 0522")
    http = FakeHTTP()
    sms = outreach.Apifon(token="tok123", secret="sec456", sender="DEMO", post=http)
    scanner = MarketScanner(lambda: {}, every_days=0, client_factory=lambda: None, credentials=lambda: False)
    c = TestClient(create_app(Store(tmp_path / "s.sqlite", seed), FakeERP(), market=scanner,
                              campaign_state=outreach.CampaignState(tmp_path / "state.json"), sms=sms))
    return c, http


def seasonal_target(c):
    r = c.get("/api/campaigns").json()
    e = r["seasonal"][0]
    it = e["items"][0]
    return e, it, it["targets"][0]


def test_price_edit_override_and_reset(env):
    c, _ = env
    p = c.get("/api/campaigns").json()["pricing"][0]
    r = c.put(f"/api/campaigns/prices/{p['MTRL']}", json={"change_pct": 0.05, "status": "approved"}, headers={"X-Actor": "ui:test"})
    assert r.status_code == 200, r.text
    row = r.json()
    assert row["change_pct"] == 0.05 and row["suggested_change_pct"] == p["change_pct"] and row["edit"]["by"] == "ui:test"
    assert c.put(f"/api/campaigns/prices/{p['MTRL']}", json={"change_pct": 0.9}).status_code == 400
    assert c.put("/api/campaigns/prices/999999", json={"change_pct": 0.01}).status_code == 404
    r = c.put(f"/api/campaigns/prices/{p['MTRL']}", json={"change_pct": None})
    assert r.json()["change_pct"] == p["change_pct"] and r.json()["edit"] is None
    assert any(a["action"] == "price_change" for a in c.get("/api/audit").json())


def test_discount_edit_flows_into_sms(env):
    c, _ = env
    e, it, t = seasonal_target(c)
    r = c.put("/api/campaigns/discounts", json={"event": e["event"], "mtrl": it["MTRL"], "disc": 12})
    assert r.status_code == 200 and r.json()["suggested_disc"] == 12 and r.json()["suggested_disc_system"] == it["suggested_disc"]
    d = c.post("/api/campaigns/sms/draft", json={"kind": "seasonal", "trdr": t["TRDR"], "mtrl": it["MTRL"], "event": e["event"]}).json()
    assert d["source"] == "template" and "-12%" in d["text"] and d["can_send"] and d["to"].startswith("+30694")
    assert c.put("/api/campaigns/discounts", json={"event": e["event"], "mtrl": it["MTRL"], "disc": 80}).status_code == 400


def test_ai_text_with_invented_number_falls_back(monkeypatch):
    f = {"kind": "seasonal", "customer": "Ταβέρνα Δυόσμος Ι.Κ.Ε.", "salesman": "Μαρία Κωνσταντίνου", "event": "Χριστούγεννα",
         "item": "Μελομακάρονα 500g", "discount_pct": "8", "valid_from": "11/12", "valid_to": "27/12"}
    monkeypatch.setattr(outreach, "has_credentials", lambda: True)

    def client(text):
        reply = NS(stop_reason="end_turn", content=[NS(type="text", text=json.dumps({"text": text}))])
        return lambda: NS(beta=NS(messages=NS(create=lambda **kw: reply)))
    good = "Ταβέρνα Δυόσμος: για τα Χριστούγεννα -8% στα Μελομακάρονα 500g, 11/12-27/12. Απαντήστε ΝΑΙ! Μαρία, DEMO ΔΙΑΝΟΜΕΣ"
    assert outreach.generate(f, client(good)) == (good, "ai")
    bad = good.replace("-8%", "-20%")                                  # αριθμός που δεν δόθηκε
    text, source = outreach.generate(f, client(bad))
    assert source == "template" and "-8%" in text and "20" not in text
    assert outreach.generate(f, client("α" * 300))[1] == "template"   # > 3 SMS


def test_apifon_request_is_signed(env):
    c, http = env
    e, it, t = seasonal_target(c)
    body = {"kind": "seasonal", "trdr": t["TRDR"], "mtrl": it["MTRL"], "event": e["event"],
            "text": "Δοκιμή προσφοράς", "idempotency_key": "k-1"}
    r = c.post("/api/campaigns/sms/send", json=body, headers={"X-Actor": "ui:test"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "sent" and r.json()["message_id"] == "msg-1"
    call = http.calls[0]
    assert call["url"] == "https://ars.apifon.com/services/api/v1/sms/send"
    sent = json.loads(call["content"])
    assert sent["subscribers"] == [{"number": "306947150522"}] and sent["message"] == {"text": "Δοκιμή προσφοράς", "dc": 2, "sender_id": "DEMO"}
    date = call["headers"]["X-ApifonWS-Date"]
    expected = base64.b64encode(hmac.new(b"sec456", f"POST\n/services/api/v1/sms/send\n{call['content'].decode()}\n{date}".encode(),
                                         hashlib.sha256).digest()).decode()
    assert call["headers"]["Authorization"] == f"ApifonWS tok123:{expected}"
    assert date.endswith(" GMT")


def test_one_click_one_sms_and_failures(env):
    c, http = env
    e, it, t = seasonal_target(c)
    body = {"kind": "seasonal", "trdr": t["TRDR"], "mtrl": it["MTRL"], "event": e["event"], "text": "Γεια", "idempotency_key": "same"}
    a = c.post("/api/campaigns/sms/send", json=body).json()
    b = c.post("/api/campaigns/sms/send", json=body).json()
    assert a["id"] == b["id"] and len(http.calls) == 1
    assert c.get("/api/campaigns").json()["sms_sent"][str(t["TRDR"])][0]["kind"] == "seasonal"
    # όχι σε πελάτη που δεν είναι στόχος της πρότασης
    assert c.post("/api/campaigns/sms/send", json={**body, "trdr": 1, "idempotency_key": "x"}).status_code == 404
    # πολύ μεγάλο κείμενο
    assert c.post("/api/campaigns/sms/send", json={**body, "text": "α" * 250, "idempotency_key": "y"}).status_code == 400
    # το Apifon απορρίπτει → 502 και καταγραφή
    http.status, http.body = 401, {"status": "401", "title": "Unauthorized"}
    r = c.post("/api/campaigns/sms/send", json={**body, "idempotency_key": "z"})
    assert r.status_code == 502 and "Unauthorized" in r.json()["message"]
    assert [s["status"] for s in c.get("/api/campaigns/sms").json()] == ["failed", "sent"]


def test_cannot_send_without_phone_or_keys(env, monkeypatch):
    c, _ = env
    e, it, t = seasonal_target(c)
    monkeypatch.delenv("SMS_DEMO_TO")
    d = c.post("/api/campaigns/sms/draft", json={"kind": "seasonal", "trdr": t["TRDR"], "mtrl": it["MTRL"], "event": e["event"]}).json()
    assert d["can_send"] is False and f"CUSTOMER_{t['TRDR']}_PHONE" in d["reason"]
    monkeypatch.setenv(f"CUSTOMER_{t['TRDR']}_PHONE", "+306900000000")
    c.app.state.sms = outreach.Apifon(token="", secret="", post=FakeHTTP())
    d = c.post("/api/campaigns/sms/draft", json={"kind": "seasonal", "trdr": t["TRDR"], "mtrl": it["MTRL"], "event": e["event"]}).json()
    assert d["can_send"] is False and "APIFON" in d["reason"]


def test_winback_and_price_promo_drafts(env):
    c, _ = env
    r = c.get("/api/campaigns").json()
    a = r["alerts"][0]
    d = c.post("/api/campaigns/sms/draft", json={"kind": "winback", "trdr": a["TRDR"]}).json()
    assert outreach._item(a["items"][0]["ITEM_NAME"]) in d["text"] and "κιβ." not in d["text"]
    promo = next(p for p in r["pricing"] if p["action"] == "promo")
    d = c.post("/api/campaigns/sms/draft", json={"kind": "price_promo", "trdr": promo["targets"][0]["TRDR"], "mtrl": promo["MTRL"]}).json()
    assert f"-{round(-promo['change_pct'] * 100)}%" in d["text"]
    inc = next(p for p in r["pricing"] if p["action"] == "increase")
    assert c.post("/api/campaigns/sms/draft", json={"kind": "price_promo", "trdr": inc["targets"][0]["TRDR"], "mtrl": inc["MTRL"]}).status_code == 400
