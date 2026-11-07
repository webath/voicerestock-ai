"""VoiceRestock App API — υλοποιεί το docs/CONTRACTS.md.

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
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StrictInt

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


class CallEvent(BaseModel):
    call_sid: str
    type: str | None = None
    status: str | None = None
    text: str | None = None
    role: str | None = None
    salesman: int | None = None
    suggestion_id: str | None = None
    erp_draft_id: str | None = None


def create_app(store: Store | None = None, erp: ERPAdapter | None = None) -> FastAPI:
    app = FastAPI(title="VoiceRestock App API")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.state.store = store or Store()
    app.state.erp = erp or MockERPAdapter()
    app.state.explanations = {}

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, e: ApiError):
        return JSONResponse({"error": e.code, "message": e.message}, status_code=e.status)

    S = lambda: app.state.store

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
            if (prev := S().idem_get(body.idempotency_key)) is not None:
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
                S().idem_put(body.idempotency_key, out)
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


@lru_cache
def _item_names() -> dict[int, str]:
    df = pd.read_csv(ROOT / "team_pack" / "data" / "MTRL.csv", encoding="utf-8-sig")
    return dict(zip(df["MTRL"].astype(int), df["NAME"]))


app = create_app() if os.environ.get("VR_NO_AUTOAPP") != "1" else None
