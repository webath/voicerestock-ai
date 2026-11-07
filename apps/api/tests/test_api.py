import json
import shutil

import pytest
from fastapi.testclient import TestClient

import os
os.environ["VR_NO_AUTOAPP"] = "1"
from app import explain as explain_mod  # noqa: E402
from app.main import create_app  # noqa: E402
from app.store import PROCESSED, Store  # noqa: E402


class FakeERP:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def create_draft(self, payload):
        self.calls.append(payload)
        if self.fail:
            return 502, {"errors": ["down"]}
        return 201, {"id": f"DRAFT-TEST-{len(self.calls):04d}", "status": "DRAFT"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    seed = tmp_path / "suggestions.json"
    shutil.copy(PROCESSED / "suggestions.json", seed)
    erp = FakeERP()
    monkeypatch.setattr(explain_mod, "_get_client", lambda: None)
    c = TestClient(create_app(Store(tmp_path / "s.sqlite", seed), erp))
    sid = c.get("/api/suggestions").json()[0]["id"]
    return c, erp, sid


def first_line(c, sid):
    s = c.get(f"/api/suggestions/{sid}").json()
    return s, s["LINES"][0]


def test_full_flow_creates_exactly_one_draft(env):
    c, erp, sid = env
    s, l = first_line(c, sid)
    r = c.post(f"/api/suggestions/{sid}/lines/{l['MTRL']}/quantity", json={"qty": l["QTY_MAX"], "version": 1},
               headers={"X-Actor": "voice:CA1"})
    assert r.status_code == 200 and r.json()["version"] == 2 and r.json()["status"] == "modified"
    tok = c.post(f"/api/suggestions/{sid}/confirm", json={"version": 2}).json()["confirmation_token"]
    body = {"confirmation_token": tok, "idempotency_key": f"CA1:{sid}:2"}
    r1 = c.post(f"/api/suggestions/{sid}/create-draft", json=body)
    r2 = c.post(f"/api/suggestions/{sid}/create-draft", json=body)
    assert r1.status_code == 200 and r1.json() == r2.json()
    assert len(erp.calls) == 1
    sent = erp.calls[0]
    assert set(sent) == {"TRDR", "CUSTOMER_CODE", "SALESMAN", "SUGGESTED_DELIVERY_DATE", "REASON", "LINES"}
    assert sent["LINES"][0]["QTY1"] == l["QTY_MAX"]
    assert c.get(f"/api/suggestions/{sid}").json()["status"] == "draft_created"
    # άλλο idempotency key μετά το draft → ίδιο draft, όχι νέο write
    r3 = c.post(f"/api/suggestions/{sid}/create-draft", json={"confirmation_token": tok, "idempotency_key": "other"})
    assert r3.json()["erp_draft_id"] == r1.json()["erp_draft_id"] and len(erp.calls) == 1


def test_qty_bounds_and_version_conflict(env):
    c, _, sid = env
    _, l = first_line(c, sid)
    assert c.post(f"/api/suggestions/{sid}/lines/{l['MTRL']}/quantity", json={"qty": l["QTY_MAX"] + 1, "version": 1}).status_code == 400
    assert c.post(f"/api/suggestions/{sid}/lines/{l['MTRL']}/quantity", json={"qty": 0, "version": 1}).status_code == 400
    assert c.post(f"/api/suggestions/{sid}/lines/{l['MTRL']}/quantity", json={"qty": 1, "version": 9}).status_code == 409
    r = c.post(f"/api/suggestions/{sid}/lines/{l['MTRL']}/quantity", json={"qty": 2.5, "version": 1})
    assert r.status_code == 422


def test_draft_requires_current_confirmation(env):
    c, erp, sid = env
    _, l = first_line(c, sid)
    assert c.post(f"/api/suggestions/{sid}/create-draft", json={"idempotency_key": "k"}).status_code == 409
    tok = c.post(f"/api/suggestions/{sid}/confirm", json={"version": 1}).json()["confirmation_token"]
    c.post(f"/api/suggestions/{sid}/lines/{l['MTRL']}/quantity", json={"qty": 1, "version": 1})  # ακυρώνει το token
    r = c.post(f"/api/suggestions/{sid}/create-draft", json={"confirmation_token": tok, "idempotency_key": "k2"})
    assert r.status_code == 409 and erp.calls == []


def test_erp_failure_is_retryable(env, tmp_path):
    c, erp, sid = env
    erp.fail = True
    tok = c.post(f"/api/suggestions/{sid}/confirm", json={"version": 1}).json()["confirmation_token"]
    r = c.post(f"/api/suggestions/{sid}/create-draft", json={"confirmation_token": tok, "idempotency_key": "a"})
    assert r.status_code == 502 and c.get(f"/api/suggestions/{sid}").json()["status"] == "failed"
    erp.fail = False
    r = c.post(f"/api/suggestions/{sid}/create-draft", json={"confirmation_token": tok, "idempotency_key": "b"})
    assert r.status_code == 200 and r.json()["status"] == "draft_created"


def test_read_endpoints(env):
    c, _, sid = env
    assert c.get("/api/health").json()["ok"]
    risk = c.get("/api/risk?limit=5").json()
    assert len(risk) == 5 and all(r["days_left"] <= 14 for r in risk)
    s = c.get(f"/api/suggestions/{sid}").json()
    assert len(c.get(f"/api/forecasts?trdr={s['TRDR']}").json()) > 0
    h = c.get(f"/api/customers/{s['TRDR']}/history?mtrl={s['LINES'][0]['MTRL']}").json()
    assert h["items"][0]["points"]
    e = c.get(f"/api/suggestions/{sid}/explanation").json()
    assert e["source"] == "template" and s["CUSTOMER_NAME"] in e["text"]
    ev = c.get("/api/evaluation").json()
    assert ev["default_model"] in {r["model"] for r in ev["rows"]}
    c.post("/api/calls/events", json={"call_sid": "CA9", "status": "discussing", "role": "agent", "text": "Γεια"})
    assert c.get("/api/calls").json()[0]["transcript"][0]["text"] == "Γεια"
    assert c.get("/api/suggestions/NOPE").status_code == 404
    cu = c.get(f"/api/customers/{s['TRDR']}").json()
    assert cu["NAME"] == s["CUSTOMER_NAME"] and cu["SALESMAN_NAME"] == s["SALESMAN_NAME"]
    assert len(c.get("/api/customers").json()) == 140
    assert c.get("/api/customers/999").status_code == 404
    assert ev["coverage"]["pairs"] == 1975


def test_reset_restores_seed(env):
    c, _, sid = env
    c.post(f"/api/suggestions/{sid}/cancel")
    assert c.get(f"/api/suggestions/{sid}").json()["status"] == "cancelled"
    c.post("/api/admin/reset")
    assert c.get(f"/api/suggestions/{sid}").json()["status"] == "proposed"


def test_explanation_falls_back_when_llm_unavailable(env, monkeypatch):
    c, _, sid = env

    class Boom:
        class beta:
            class messages:
                @staticmethod
                def create(**kw):
                    raise TypeError("Could not resolve authentication method")

    monkeypatch.setattr(explain_mod, "_get_client", lambda: Boom)
    assert c.get(f"/api/suggestions/{sid}/explanation").json()["source"] == "template"


def test_new_forecast_run_reloads_proposals(tmp_path):
    seed = tmp_path / "suggestions.json"
    shutil.copy(PROCESSED / "suggestions.json", seed)
    st = Store(tmp_path / "s.sqlite", seed)
    sid = st.all()[0]["id"]
    s = st.get(sid); s["status"] = "cancelled"; st.put(s)
    assert Store(tmp_path / "s.sqlite", seed).get(sid)["status"] == "cancelled"      # ίδιο seed → κρατά state
    data = json.loads(seed.read_text(encoding="utf-8")); data["suggestions"][0]["REASON"] = "νέο τρέξιμο"
    seed.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    fresh = Store(tmp_path / "s.sqlite", seed)                                     # νέο seed → reload
    assert fresh.get(sid)["status"] == "proposed"


def test_idempotency_key_is_scoped_to_suggestion(env):
    c, erp, _ = env
    a, b = [s["id"] for s in c.get("/api/suggestions").json()[:2]]
    for sid in (a, b):
        tok = c.post(f"/api/suggestions/{sid}/confirm", json={"version": 1}).json()["confirmation_token"]
        r = c.post(f"/api/suggestions/{sid}/create-draft", json={"confirmation_token": tok, "idempotency_key": "same-key"})
        assert r.status_code == 200
    assert len(erp.calls) == 2                                   # δύο διαφορετικά drafts
    assert c.get(f"/api/suggestions/{a}").json()["erp_draft_id"] != c.get(f"/api/suggestions/{b}").json()["erp_draft_id"]


def test_value_follows_quantity(env):
    c, erp, sid = env
    s = c.get(f"/api/suggestions/{sid}").json()
    l = s["LINES"][0]
    assert s["VALUE"] == round(sum(x["PRICE"] * x["QTY1"] for x in s["LINES"]), 2)
    n = c.post(f"/api/suggestions/{sid}/lines/{l['MTRL']}/quantity", json={"qty": l["QTY1"] + 1, "version": 1}).json()
    assert round(n["VALUE"] - s["VALUE"], 2) == round(l["PRICE"], 2)
    tok = c.post(f"/api/suggestions/{sid}/confirm", json={"version": 2}).json()["confirmation_token"]
    c.post(f"/api/suggestions/{sid}/create-draft", json={"confirmation_token": tok, "idempotency_key": "v"})
    assert "VALUE" not in erp.calls[0] and "PRICE" not in erp.calls[0]["LINES"][0]   # το ERP payload δεν αλλάζει
