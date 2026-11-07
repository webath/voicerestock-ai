"""Ανάγνωση δεδομένων από το ERP API (SoftOne-style, βλ. team_pack/README_challenge.md §API) — όχι από τα CSV.

    GET /api/customers · /api/items · /api/salesmen · /api/promotions
    GET /api/saldoc?page=&pageSize=1000   → headers με φωλιασμένο LINES (σελιδοποίηση)

Επιστρέφει τους ίδιους πίνακες με τα CSV (TRDR, MTRL, PRSN, PROMO, SALDOC, MTRLINES), ώστε ο καθαρισμός να είναι κοινός.
Μόνο stdlib (urllib) — καμία νέα εξάρτηση.
"""
from __future__ import annotations

import json
import math
import os
from typing import Callable
from urllib.request import urlopen

import pandas as pd

ERP_URL = os.environ.get("ERP_BASE_URL", "http://localhost:8080").rstrip("/")
PAGE_SIZE = 1000   # μέγιστο του API


def _get(base: str, path: str, timeout: float = 30.0):
    with urlopen(f"{base}{path}", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch(base: str = ERP_URL, progress: Callable[[int, int], None] | None = None) -> dict[str, pd.DataFrame]:
    base = base.rstrip("/")
    raw = {"TRDR": pd.DataFrame(_get(base, "/api/customers")), "MTRL": pd.DataFrame(_get(base, "/api/items")),
           "PRSN": pd.DataFrame(_get(base, "/api/salesmen")), "PROMO": pd.DataFrame(_get(base, "/api/promotions"))}
    headers, lines, page, pages = [], [], 1, 1
    while page <= pages:
        r = _get(base, f"/api/saldoc?page={page}&pageSize={PAGE_SIZE}")
        pages = max(1, math.ceil(r["total"] / PAGE_SIZE))
        for h in r["items"]:
            for l in h.pop("LINES", []):
                lines.append({"FINDOC": h["FINDOC"], **l})
            headers.append(h)
        if progress:
            progress(page, pages)
        page += 1
    raw["SALDOC"] = pd.DataFrame(headers)
    raw["MTRLINES"] = pd.DataFrame(lines)
    return {k: _normalize(v) for k, v in raw.items()}


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """JSON → ίδιοι τύποι με το pd.read_csv: "" = κενό, αριθμητικές στήλες ως αριθμοί (π.χ. PROMO.MTRL για προσφορά κατηγορίας)."""
    df = df.replace("", pd.NA)
    for c in df.columns[df.dtypes == object]:
        try:
            df[c] = pd.to_numeric(df[c])
        except (ValueError, TypeError):
            df[c] = df[c].astype(object).where(df[c].notna(), None)
    return df
