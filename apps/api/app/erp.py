"""ERP adapter. Σήμερα: Revival mock ERP (POST /api/draft-orders). Αντικαθίσταται από πραγματικό adapter αργότερα."""
from __future__ import annotations

import os
from typing import Protocol

import httpx

ERP_LINE_KEYS = ("MTRL", "ITEM_CODE", "QTY1", "PREDICTED_DEPLETION_DATE", "CONFIDENCE")
ERP_HEADER_KEYS = ("TRDR", "CUSTOMER_CODE", "SALESMAN", "SUGGESTED_DELIVERY_DATE", "REASON")


def to_erp_payload(s: dict) -> dict:
    """Suggestion → ακριβώς το σχήμα του sample_suggested_order.json."""
    return {**{k: s[k] for k in ERP_HEADER_KEYS},
            "LINES": [{k: l[k] for k in ERP_LINE_KEYS} for l in s["LINES"]]}


class ERPAdapter(Protocol):
    def create_draft(self, payload: dict) -> tuple[int, dict]: ...


class MockERPAdapter:
    def __init__(self, base_url: str | None = None):
        self.base = (base_url or os.environ.get("ERP_BASE_URL", "http://localhost:8080")).rstrip("/")

    def create_draft(self, payload: dict) -> tuple[int, dict]:
        try:
            r = httpx.post(f"{self.base}/api/draft-orders", json=payload, timeout=10)
            return r.status_code, r.json()
        except httpx.HTTPError as e:
            return 502, {"errors": [f"ERP unreachable: {e}"]}
