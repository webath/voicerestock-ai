"""VORA App API — υλοποιεί το docs/CONTRACTS.md.

    uv run uvicorn app.main:app --port 8000
Προϋπόθεση: `cd services/forecast && uv run python -m forecast.ingest && uv run python -m forecast.suggest`
"""
from __future__ import annotations

import copy
import json
import logging
import os
import secrets
import uuid
from functools import lru_cache

import pandas as pd
from fastapi import FastAPI, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, StrictInt

from . import assistant as ai
from .agent import AgentRunner
from .erp import ERPAdapter, MockERPAdapter, to_erp_payload
from .explain import explain
from .store import PROCESSED, ROOT, Store

logging.basicConfig(level=logging.INFO)
URGENCY_ORDER = {"high": 0, "medium": 1, "low": 2}
LOCKED = {"draft_created", "posting", "cancelled"}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


class QtyBody(BaseModel):
    qty: StrictInt
    version: int


class ConfirmBody(BaseModel):
    version: int


class DraftBody(BaseModel):
    confirmation_token: str | None = None
    idempotency_key: str


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatBody(BaseModel):
    messages: list[ChatMessage]
    salesman: int | None = None


class MessageBody(BaseModel):
    channel: str = "sms"


class CallEvent(BaseModel):
    call_sid: str
    type: str | None = None
    status: str | None = None
    text: str | None = None
    role: str | None = None
    salesman: int | None = None
    suggestion_id: str | None = None
    erp_draft_id: str | None = None


def create_app(store: Store | None = None, erp: ERPAdapter | None = None, agent: AgentRunner | None = None) -> FastAPI:
    app = FastAPI(title="VORA App API")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.state.store = store or Store()
    app.state.erp = erp or MockERPAdapter()
    app.state.explanations = {}
    app.state.ai_cache = {}

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, e: ApiError):
        return JSONResponse({"error": e.code, "message": e.message}, status_code=e.status)

    S = lambda: app.state.store

    def after_agent(run: dict) -> dict:
        """Ο agent έγραψε νέα αρχεία → φρέσκα caches· νέες προτάσεις μόνο αν άλλαξαν."""
        for f in (_forecasts, _daily, _customers, _salesman_names, _item_names):
            f.cache_clear()
        app.state.ai_cache.clear()
        changed = S().reload_if_changed()
        if changed:
            app.state.explanations.clear()
        n = len(S().all())
        S().audit("agent", "agent_run", None, f"{run.get('id')}: {'νέες προτάσεις' if changed else 'χωρίς αλλαγές'}")
        return {"reloaded": changed, "suggestions": n,
                "detail": (f"{n} νέες προτάσεις στο dashboard και στον voice agent" if changed else
                           f"Οι {n} προτάσεις δεν άλλαξαν — εγκρίσεις και drafts μένουν ως έχουν")
                          + " · draft στο ERP μόνο όταν εγκρίνει ο πωλητής"}

    app.state.agent = agent or AgentRunner(after_agent)
    if agent is not None and getattr(agent, "on_finish", None) is None:
        agent.on_finish = after_agent

    def must_get(sid: str) -> dict:
        s = S().get(sid)
        if not s:
            raise ApiError(404, "not_found", "suggestion not found")
        return s

    # ---------------- read ----------------
    @app.get("/api/health")
    def health():
        return {"ok": True, "suggestions": len(S().all())}

    @app.get("/api/salesmen")
    def salesmen():
        df = pd.read_csv(ROOT / "team_pack" / "data" / "PRSN.csv", encoding="utf-8-sig")
        return [{"PRSN": int(r.PRSN), "NAME": r.NAME, "phone": os.environ.get(f"SALESMAN_{int(r.PRSN)}_PHONE")}
                for r in df.itertuples()]

    @app.get("/api/suggestions")
    def suggestions(salesman: int | None = None, status: str | None = None):
        rows = [s for s in S().all() if (salesman is None or s["SALESMAN"] == salesman)
                and (status is None or s["status"] == status)]
        return sorted(rows, key=lambda s: (URGENCY_ORDER[s["urgency"]], s["LINES"][0]["PREDICTED_DEPLETION_DATE"]))

    @app.get("/api/suggestions/{sid}")
    def suggestion(sid: str):
        return must_get(sid)

    @app.get("/api/suggestions/{sid}/explanation")
    def explanation(sid: str):
        s = must_get(sid)
        key = (sid, s["version"])
        if key not in app.state.explanations:
            app.state.explanations[key] = explain(s)
        return app.state.explanations[key]

    @app.get("/api/risk")
    def risk(salesman: int | None = None, limit: int = Query(50, le=2000)):
        cust = _customers()
        sug_by_trdr = {s["TRDR"]: s["id"] for s in S().all()}
        rows = []
        for f in _forecasts():
            if f["urgency"] not in URGENCY_ORDER or f["days_left"] is None or f["days_left"] > 14:
                continue
            c = cust[f["TRDR"]]
            if salesman is not None and c["SALESMAN"] != salesman:
                continue
            rows.append({**f, "CUSTOMER_NAME": c["NAME"], "CUSTOMER_CATEGORY": c["TRDCATEGORY"], "AREA": c["AREA"],
                         "SALESMAN": c["SALESMAN"], "suggestion_id": sug_by_trdr.get(f["TRDR"])})
        rows.sort(key=lambda r: (r["PREDICTED_DEPLETION_DATE"], -r["CONFIDENCE"]))
        return rows[:limit]

    @app.get("/api/customers")
    def customers():
        return [_customer_out(c) for c in _customers().values()]

    @app.get("/api/customers/{trdr}")
    def customer(trdr: int):
        c = _customers().get(trdr)
        if not c:
            raise ApiError(404, "not_found", "customer not found")
        return _customer_out(c)

    @app.get("/api/forecasts")
    def forecasts(trdr: int):
        return [f for f in _forecasts() if f["TRDR"] == trdr]

    @app.get("/api/customers/{trdr}/history")
    def history(trdr: int, mtrl: int | None = None):
        d = _daily()
        x = d[d["TRDR"] == trdr]
        if x.empty:
            raise ApiError(404, "not_found", "customer not found")
        if mtrl is not None:
            x = x[x["MTRL"] == mtrl]
        names = _item_names()
        return {"TRDR": trdr, "items": [
            {"MTRL": int(m), "ITEM_NAME": names.get(int(m)),
             "points": [{"date": dt.strftime("%Y-%m-%d"), "qty": float(q)} for dt, q in zip(g["DATE"], g["qty"])]}
            for m, g in x.groupby("MTRL")]}

    @app.get("/api/evaluation")
    def evaluation():
        return json.loads((PROCESSED / "evaluation.json").read_text(encoding="utf-8"))

    @app.get("/api/calls")
    def calls():
        return S().calls()

    @app.get("/api/audit")
    def audit(limit: int = 200):
        return S().audit_log(limit)

    # ---------------- write ----------------
    @app.post("/api/suggestions/{sid}/lines/{mtrl}/quantity")
    def change_qty(sid: str, mtrl: int, body: QtyBody, x_actor: str = Header("unknown")):
        with S().lock:
            s = must_get(sid)
            line = next((l for l in s["LINES"] if l["MTRL"] == mtrl), None)
            if not line:
                raise ApiError(404, "not_found", f"MTRL {mtrl} not in suggestion")
            if s["status"] in LOCKED:
                raise ApiError(409, "locked", f"status is {s['status']}")
            if body.version != s["version"]:
                raise ApiError(409, "version_conflict", f"current version is {s['version']}")
            if not line["QTY_MIN"] <= body.qty <= line["QTY_MAX"]:
                raise ApiError(400, "qty_out_of_bounds", f"qty must be integer in {line['QTY_MIN']}..{line['QTY_MAX']}")
            line["QTY1"] = body.qty
            s["version"] += 1
            s["status"] = "modified"
            S().drop_tokens(sid)                    # παλιές επιβεβαιώσεις άκυρες
            S().put(s)
            S().audit(x_actor, f"quantity {mtrl}={body.qty}", sid, f"v{s['version']}")
            return s

    @app.post("/api/suggestions/{sid}/confirm")
    def confirm(sid: str, body: ConfirmBody, x_actor: str = Header("unknown")):
        with S().lock:
            s = must_get(sid)
            if s["status"] not in ("proposed", "modified", "confirmed", "failed"):
                raise ApiError(409, "locked", f"status is {s['status']}")
            if body.version != s["version"]:
                raise ApiError(409, "version_conflict", f"current version is {s['version']}")
            tok = secrets.token_urlsafe(16)
            S().new_token(tok, sid, s["version"])
            s["status"] = "confirmed"
            S().put(s)
            S().audit(x_actor, "confirm", sid, f"v{s['version']}")
            return {"confirmation_token": tok, "snapshot": copy.deepcopy(s)}

    @app.post("/api/suggestions/{sid}/cancel")
    def cancel(sid: str, x_actor: str = Header("unknown")):
        with S().lock:
            s = must_get(sid)
            if s["status"] in ("draft_created", "posting"):
                raise ApiError(409, "locked", f"status is {s['status']}")
            s["status"] = "cancelled"
            S().drop_tokens(sid)
            S().put(s)
            S().audit(x_actor, "cancel", sid, "ok")
            return s

    @app.post("/api/suggestions/{sid}/create-draft")
    def create_draft(sid: str, body: DraftBody, x_actor: str = Header("unknown")):
        cid = str(uuid.uuid4())
        with S().lock:
            # Το key ισχύει ΜΟΝΟ για αυτή την πρόταση: το ίδιο key σε άλλη πρόταση δεν επιστρέφει ξένο draft.
            idem = f"{sid}|{body.idempotency_key}"
            if (prev := S().idem_get(idem)) is not None:
                return prev
            s = must_get(sid)
            if s["status"] == "draft_created":
                return {"erp_draft_id": s["erp_draft_id"], "status": "draft_created"}
            if S().token(body.confirmation_token) != (sid, s["version"]):
                raise ApiError(409, "not_confirmed", "missing/stale confirmation_token")
            s["status"] = "posting"
            S().put(s)
            # Το POST γίνεται μέσα στο lock: διπλά/ταυτόχρονα requests δεν μπορούν να γράψουν δεύτερο draft.
            code, resp = app.state.erp.create_draft(to_erp_payload(s))
            if code == 201:
                s["status"] = "draft_created"
                s["erp_draft_id"] = resp["id"]
                S().put(s)
                S().drop_tokens(sid)
                out = {"erp_draft_id": resp["id"], "status": "draft_created"}
                S().idem_put(idem, out)
                S().audit(x_actor, "create-draft", sid, resp["id"], cid)
                return out
            s["status"] = "failed"
            S().put(s)
            S().audit(x_actor, "create-draft", sid, f"ERP {code}", cid)
            raise ApiError(502, "erp_error", json.dumps(resp, ensure_ascii=False))

    @app.post("/api/calls/events")
    def call_event(ev: CallEvent):
        S().call_event(ev.model_dump())
        return {"ok": True}

    # ---------------- AI βοηθός (μόνο ανάγνωση) ----------------
    data = ai.Data(suggestions=lambda: S().all(), forecasts=_forecasts, customers=_customers,
                   evaluation=lambda: json.loads((PROCESSED / "evaluation.json").read_text(encoding="utf-8")),
                   salesmen=_salesman_names)

    @app.post("/api/assistant")
    def assistant(body: ChatBody):
        hist = [m.model_dump() for m in body.messages]
        return StreamingResponse(ai.chat_stream(data, hist, body.salesman), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/briefing")
    def briefing(salesman: int):
        if salesman not in _salesman_names():
            raise ApiError(404, "not_found", "unknown salesman")
        state = tuple(sorted((s["id"], s["version"], s["status"]) for s in S().all() if s["SALESMAN"] == salesman))
        key = ("briefing", salesman, hash(state))
        if key not in app.state.ai_cache:
            app.state.ai_cache[key] = ai.briefing(data, salesman)
        return app.state.ai_cache[key]

    @app.post("/api/suggestions/{sid}/customer-message")
    def customer_message(sid: str, body: MessageBody):
        if body.channel not in ("sms", "email"):
            raise ApiError(400, "bad_request", "channel must be sms or email")
        s = must_get(sid)
        key = ("msg", sid, s["version"], body.channel)
        if key not in app.state.ai_cache:
            app.state.ai_cache[key] = ai.customer_message(s, body.channel)
        return app.state.ai_cache[key]

    # ---------------- agent ----------------
    @app.get("/api/agent")
    def agent_state():
        return app.state.agent.state()

    @app.post("/api/agent/run", status_code=202)
    def agent_run():
        run = app.state.agent.start("manual")
        if run is None:
            raise ApiError(409, "agent_running", "ο agent τρέχει ήδη")
        return run

    @app.post("/api/admin/reset")
    def reset(x_actor: str = Header("unknown")):
        n = S().reset()
        app.state.explanations.clear()
        S().audit(x_actor, "reset", None, f"{n} suggestions")
        return {"ok": True, "suggestions": n}

    return app


# ---------------- cached reference data ----------------
@lru_cache
def _forecasts() -> list[dict]:
    return json.loads((PROCESSED / "forecasts.json").read_text(encoding="utf-8"))["forecasts"]


@lru_cache
def _daily() -> pd.DataFrame:
    return pd.read_parquet(PROCESSED / "daily.parquet")


@lru_cache
def _customers() -> dict[int, dict]:
    df = pd.read_csv(ROOT / "team_pack" / "data" / "TRDR.csv", encoding="utf-8-sig")
    return {int(r["TRDR"]): r for r in df.to_dict("records")}


def _customer_out(c: dict) -> dict:
    names = _salesman_names()
    return {"TRDR": int(c["TRDR"]), "CODE": c["CODE"], "NAME": c["NAME"], "TRDCATEGORY": c["TRDCATEGORY"],
            "AREA": c["AREA"], "CITY": c["CITY"], "SALESMAN": int(c["SALESMAN"]),
            "SALESMAN_NAME": names.get(int(c["SALESMAN"])), "INSDATE": c["INSDATE"],
            "cold_start": c["INSDATE"] >= "2026-01-01"}


@lru_cache
def _salesman_names() -> dict[int, str]:
    df = pd.read_csv(ROOT / "team_pack" / "data" / "PRSN.csv", encoding="utf-8-sig")
    return dict(zip(df["PRSN"].astype(int), df["NAME"]))


@lru_cache
def _item_names() -> dict[int, str]:
    df = pd.read_csv(ROOT / "team_pack" / "data" / "MTRL.csv", encoding="utf-8-sig")
    return dict(zip(df["MTRL"].astype(int), df["NAME"]))


app = create_app() if os.environ.get("VR_NO_AUTOAPP") != "1" else None
