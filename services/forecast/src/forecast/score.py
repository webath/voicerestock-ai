"""Αναπαραγωγή της βαθμολόγησης του README §7.

pred / truth: DataFrames με στήλες TRDR, MTRL, DATE (NaT = καμία εξάντληση).
"""
from __future__ import annotations

import pandas as pd

MISSING_PENALTY = 60
AT_RISK_DAYS = 14


def pair_errors(pred: pd.DataFrame, truth: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    horizon_end = cutoff + pd.Timedelta(days=90)
    m = truth.rename(columns={"DATE": "true"}).merge(
        pred.rename(columns={"DATE": "pred"}), on=["TRDR", "MTRL"], how="left", indicator=True)
    missing = m["_merge"] == "left_only"
    t, p = m["true"], m["pred"]
    t_none = t.isna() | (t >= horizon_end)
    p_none = p.isna() | (p >= horizon_end)
    days = lambda s: s.dt.days.astype(float)
    err = pd.Series(0.0, index=m.index)
    both = ~t_none & ~p_none
    err[both] = days((p - t).abs())[both]
    only_p = t_none & ~p_none
    err[only_p] = days(horizon_end - p)[only_p]
    only_t = ~t_none & p_none
    err[only_t] = days(horizon_end - t)[only_t]
    err[missing] = MISSING_PENALTY
    m["err"] = err
    return m.drop(columns="_merge")


def score(pred: pd.DataFrame, truth: pd.DataFrame, cutoff: pd.Timestamp) -> dict:
    m = pair_errors(pred, truth, cutoff)
    risk_end = cutoff + pd.Timedelta(days=AT_RISK_DAYS)
    true_risk = m["true"].notna() & (m["true"] <= risk_end)
    pred_risk = m["pred"].notna() & (m["pred"] <= risk_end)
    tp = (true_risk & pred_risk).sum()
    return {
        "n": len(m),
        "mae": round(m["err"].mean(), 3),
        "within_3": round((m["err"] <= 3).mean(), 3),
        "within_7": round((m["err"] <= 7).mean(), 3),
        "at_risk_precision": round(tp / pred_risk.sum(), 3) if pred_risk.sum() else None,
        "at_risk_recall": round(tp / true_risk.sum(), 3) if true_risk.sum() else None,
    }
