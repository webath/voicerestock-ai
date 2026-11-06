"""Γράφει το submission στο ακριβές format του submission_template.csv.

    uv run python -m forecast.submit [--model hybrid_0.7] [--team <όνομα>]
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from .ingest import CUTOFF, DATA, ROOT, load
from .backtest import history
from .models import DEFAULT_MODEL, REGISTRY


def build(model: str = DEFAULT_MODEL) -> pd.DataFrame:
    d = load()
    template = pd.read_csv(DATA / "submission_template.csv", encoding="utf-8-sig")
    tg = template[["TRDR", "MTRL"]]
    pred = REGISTRY[model](d, history(d, CUTOFF), tg, CUTOFF)
    out = tg.merge(pred, on=["TRDR", "MTRL"], how="left", validate="one_to_one")
    horizon_end = CUTOFF + pd.Timedelta(days=90)
    out.loc[out["DATE"] >= horizon_end, "DATE"] = pd.NaT
    out["PREDICTED_DEPLETION_DATE"] = out["DATE"].dt.strftime("%Y-%m-%d")
    out["SUGGESTED_QTY"] = np.nan
    out = out[list(template.columns)]
    assert len(out) == len(template) == 1975
    assert (out[["TRDR", "MTRL"]].values == template[["TRDR", "MTRL"]].values).all()
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL, choices=list(REGISTRY))
    ap.add_argument("--team", default="voicerestock")
    a = ap.parse_args()
    out = build(a.model)
    path = ROOT / "submissions" / f"team_{a.team}.csv"
    out.to_csv(path, index=False, encoding="utf-8")
    n_date = out["PREDICTED_DEPLETION_DATE"].notna().sum()
    risk = (pd.to_datetime(out["PREDICTED_DEPLETION_DATE"]) <= CUTOFF + pd.Timedelta(days=14)).sum()
    print(f"{path.relative_to(ROOT)}: {len(out)} rows, {n_date} with date, {len(out) - n_date} blank, {risk} at-risk (≤ 2026-11-14)")


if __name__ == "__main__":
    main()
