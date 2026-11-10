"""Regression: ανανέωση forecast δεν σβήνει δουλειά πωλητή ή ιστορικό ERP."""
import copy
import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Event

os.environ["VR_NO_AUTOAPP"] = "1"
os.environ["AGENT_DAILY_AT"] = ""

import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.store import Store, ROOT


class ERP:
    def __init__(self):
        self.calls = []

    def create_draft(self, payload):
        self.calls.append(copy.deepcopy(payload))
        return 201, {"id": f"DRAFT-{len(self.calls)}", "status": "DRAFT"}


@pytest.fixture
def env(tmp_path):
    data = json.loads((ROOT / "fixtures/suggestions.sample.json").read_text())
    seed = tmp_path / "suggestions.json"
    seed.write_text(json.dumps(data))
    store = Store(tmp_path / "state.sqlite", seed)
    erp = ERP()
    return TestClient(create_app(store, erp), headers={"X-Actor": "test"}), store, erp, data, seed


def approve(c, s, key="original"):
    tok = c.post(f"/api/suggestions/{s['id']}/confirm", json={"version": s["version"]}).json()["confirmation_token"]
    body = {"confirmation_token": tok, "idempotency_key": key}
    out = c.post(f"/api/suggestions/{s['id']}/create-draft", json=body)
    assert out.status_code == 200
    return body, out.json()


def test_refresh_preserves_draft_retry_calls_audit_and_restart(env, tmp_path):
    c, st, erp, data, seed = env
    a, b = data["suggestions"][:2]
    body, draft = approve(c, a)
    st.call_event({"call_sid": "existing", "status": "ended", "suggestion_id": a["id"]})
    before = st.audit_log()
    # Αλλαγή σε διαφορετικό πελάτη.
    b["REASON"] += " νέα πρόβλεψη"
    seed.write_text(json.dumps(data))
    assert st.reload_if_changed()
    assert st.get(a["id"])["erp_draft_id"] == draft["erp_draft_id"]
    assert st.get(a["id"])["status"] == "draft_created"
    assert len(st.calls()) == 1
    assert all(e in st.audit_log() for e in before)
    assert c.post(f"/api/suggestions/{a['id']}/create-draft", json=body).json() == draft
    assert len(erp.calls) == 1
    # Ακόμη και αλλαγή της ίδιας πρότασης δεν επαναφέρει draft σε proposed.
    a["LINES"][0]["QTY1"] += 1
    a["LINES"][0]["QTY_RECOMMENDED"] += 1
    seed.write_text(json.dumps(data))
    assert st.reload_if_changed()
    assert st.get(a["id"])["status"] == "draft_created"
    assert st.get(a["id"])["forecast_update_available"]
    restarted = Store(tmp_path / "state.sqlite", seed)
    assert restarted.get(a["id"])["erp_draft_id"] == draft["erp_draft_id"]
    assert len(restarted.calls()) == 1


def test_only_changed_proposal_loses_confirmation_and_keeps_valid_manual_qty(env):
    c, st, _, data, seed = env
    a, b = data["suggestions"][:2]
    l = a["LINES"][0]
    qty = l["QTY1"] + 1
    c.post(f"/api/suggestions/{a['id']}/lines/{l['MTRL']}/quantity", json={"qty": qty, "version": 1})
    ta = c.post(f"/api/suggestions/{a['id']}/confirm", json={"version": 2}).json()["confirmation_token"]
    tb = c.post(f"/api/suggestions/{b['id']}/confirm", json={"version": 1}).json()["confirmation_token"]
    a["REASON"] += " νέα ημερομηνία"
    seed.write_text(json.dumps(data))
    st.reload_if_changed()
    fresh = st.get(a["id"])
    assert fresh["version"] == 3 and fresh["status"] == "modified"
    assert fresh["LINES"][0]["QTY1"] == qty
    assert st.token(ta) is None
    assert st.token(tb) == (b["id"], 1)
    assert c.post(f"/api/suggestions/{a['id']}/confirm", json={"version": 2}).status_code == 409
    assert st.changes()["ids"] == [a["id"]]


def test_formatting_only_preserves_tokens_and_versions(env):
    c, st, _, data, seed = env
    a = data["suggestions"][0]
    tok = c.post(f"/api/suggestions/{a['id']}/confirm", json={"version": 1}).json()["confirmation_token"]
    data["suggestions"].reverse()
    a["LINES"].reverse()
    seed.write_text(json.dumps(data, indent=4))
    assert st.reload_if_changed() is False
    assert st.token(tok) == (a["id"], 1)
    assert st.get(a["id"])["status"] == "confirmed"


def test_withdrawal_keeps_history_invalidates_token_and_reappearance_versions(env):
    c, st, _, data, seed = env
    a = data["suggestions"].pop(0)
    tok = c.post(f"/api/suggestions/{a['id']}/confirm", json={"version": 1}).json()["confirmation_token"]
    seed.write_text(json.dumps(data)); st.reload_if_changed()
    assert st.get(a["id"])["forecast_withdrawn"]
    assert st.get(a["id"])["version"] == 2
    assert st.token(tok) is None
    data["suggestions"].append(a)
    seed.write_text(json.dumps(data)); st.reload_if_changed()
    s = st.get(a["id"])
    assert s["version"] == 3 and s["status"] == "proposed" and s["forecast_active"]


def test_new_bounds_discard_invalid_manual_qty(env):
    c, st, _, data, seed = env
    a = data["suggestions"][0]; l = a["LINES"][0]
    qty = l["QTY_MAX"]
    c.post(f"/api/suggestions/{a['id']}/lines/{l['MTRL']}/quantity", json={"qty": qty, "version": 1})
    l["QTY_MAX"] = qty - 1
    seed.write_text(json.dumps(data)); st.reload_if_changed()
    assert st.get(a["id"])["LINES"][0]["QTY1"] == l["QTY_RECOMMENDED"]
    assert st.get(a["id"])["status"] == "proposed"


def test_trace_snapshots_and_metrics_are_measured(env):
    c, st, erp, data, _ = env
    a = data["suggestions"][0]; l = a["LINES"][0]
    changed = c.post(f"/api/suggestions/{a['id']}/lines/{l['MTRL']}/quantity", json={"qty": l["QTY1"] + 1, "version": 1}).json()
    c.post("/api/calls/events", json={"call_sid": "c", "type": "confirmation", "suggestion_id": a["id"], "text": "Ναι, επιβεβαιώνω", "role": "user"})
    _, draft = approve(c, changed)
    st.call_event({"call_sid": "c", "status": "ended"})
    trace = c.get(f"/api/suggestions/{a['id']}/trace").json()
    assert trace["erp_draft_id"] == draft["erp_draft_id"]
    assert {e["action"] for e in trace["events"]} >= {"forecast_created", "confirm", "create-draft", "voice_confirmation"}
    actions = [e["action"] for e in trace["events"]]
    assert actions.index("confirm") < actions.index("create-draft")
    initial = next(e["snapshot"] for e in trace["events"] if e["action"] == "forecast_created")
    final = next(e["snapshot"] for e in trace["events"] if e["action"] == "create-draft")
    assert initial["LINES"][0]["QTY1"] + 1 == final["LINES"][0]["QTY1"]
    assert "confirmation_token" not in json.dumps(trace)
    m = c.get("/api/operations").json()
    assert m["drafts"] == m["modified_drafts"] == m["calls"] == m["timed_calls"] == 1
    assert m["draft_value_eur"] == st.get(a["id"])["VALUE"]
    assert m["average_call_seconds"] >= 0 and len(erp.calls) == 1
    assert c.get("/api/suggestions/missing/trace").status_code == 404


def test_legacy_database_migrates_without_reset(env, tmp_path):
    c, st, _, data, seed = env
    a = data["suggestions"][0]
    _, draft = approve(c, a)
    st.db.close()
    # Παλιό schema: audit χωρίς snapshots και χωρίς forecast_seeds.
    db = sqlite3.connect(tmp_path / "state.sqlite")
    db.execute("DROP TABLE forecast_seeds")
    db.execute("ALTER TABLE audit DROP COLUMN snapshot")
    db.commit(); db.close()
    migrated = Store(tmp_path / "state.sqlite", seed)
    assert migrated.get(a["id"])["erp_draft_id"] == draft["erp_draft_id"]
    assert migrated.audit_log()


def test_refresh_waits_for_inflight_erp_write(env):
    c, st, erp, data, seed = env
    a = data["suggestions"][0]
    tok = c.post(f"/api/suggestions/{a['id']}/confirm", json={"version": 1}).json()["confirmation_token"]
    entered, release = Event(), Event()
    original = erp.create_draft

    def slow(payload):
        entered.set()
        assert release.wait(5)
        return original(payload)

    erp.create_draft = slow
    with ThreadPoolExecutor(max_workers=2) as pool:
        write = pool.submit(c.post, f"/api/suggestions/{a['id']}/create-draft", json={"confirmation_token": tok, "idempotency_key": "inflight"})
        assert entered.wait(5)
        a["REASON"] += " updated"
        seed.write_text(json.dumps(data))
        refresh = pool.submit(st.reload_if_changed)
        release.set()
        assert write.result(5).status_code == 200
        assert refresh.result(5)
    assert st.get(a["id"])["status"] == "draft_created"
    assert st.get(a["id"])["erp_draft_id"] == "DRAFT-1"
    assert len(erp.calls) == 1


def test_trace_orders_equal_timestamp_events_by_sequence(env):
    c, st, _, data, _ = env
    a = data["suggestions"][0]
    approve(c, a)
    with st.db:
        st.db.execute("UPDATE audit SET at = '2026-11-07T10:00:00Z'")
    events = c.get(f"/api/suggestions/{a['id']}/trace").json()["events"]
    assert [e["action"] for e in events] == ["forecast_created", "confirm", "create-draft"]
