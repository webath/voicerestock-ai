"""Ιστορικός κύκλος μετά από προσφορά, με συρρίκνωση ώστε λίγες αγορές να μην κυριαρχούν.

Μόνο ολοκληρωμένα διαστήματα πριν το cutoff. Κατηγορία → πελάτης/είδος → fallback 1,8.
Οι σταθερές ελέγχθηκαν με το experiments/validate_adaptive_promo.py.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CATEGORY_PRIOR = 30
PAIR_PRIOR = 5
LOOKBACK_DAYS = 365


def adaptive_promo_multiplier(history: pd.DataFrame, items: pd.DataFrame, intervals: pd.DataFrame,
                              targets: pd.DataFrame, cutoff: pd.Timestamp, fallback: float = 1.8) -> np.ndarray:
    """Ένας συντελεστής για κάθε row των targets, με την ίδια σειρά (όχι join στο index τους)."""
    out = np.full(len(targets), fallback, dtype=float)
    if "in_promo" not in history or history.empty:
        return out
    buys = history[(history["DATE"] <= cutoff) & (history["gross"] > 0)].sort_values("DATE").copy()
    if buys.empty:
        return out
    # Η επόμενη αγορά πρέπει ήδη να έχει συμβεί, αλλιώς δεν χρησιμοποιείται ως training event.
    buys["gap"] = buys.groupby(["TRDR", "MTRL"])["DATE"].shift(-1).sub(buys["DATE"]).dt.days
    b = buys.merge(intervals, on=["TRDR", "MTRL"], how="left", validate="many_to_one")
    b = b.merge(items[["MTRL", "MTRCATEGORY"]], on="MTRL", how="left", validate="many_to_one")
    b["ratio"] = b["gap"] / b["interval"]
    b = b[b["in_promo"] & b["gap"].notna() & b["ratio"].between(0.5, 4)
          & (b["DATE"] > cutoff - pd.Timedelta(days=LOOKBACK_DAYS))]
    if b.empty:
        return out
    cat = b.groupby("MTRCATEGORY")["ratio"].agg(["median", "count"])
    cat["mult"] = ((cat["median"] * cat["count"] + fallback * CATEGORY_PRIOR)
                   / (cat["count"] + CATEGORY_PRIOR)).clip(1, 3)
    categories = targets["MTRL"].map(items.set_index("MTRL")["MTRCATEGORY"])
    category_prior = categories.map(cat["mult"]).fillna(fallback).to_numpy(float)
    pair = b.groupby(["TRDR", "MTRL"])["ratio"].agg(["median", "count"])
    ix = pd.MultiIndex.from_frame(targets[["TRDR", "MTRL"]])
    n = ix.map(pair["count"]).fillna(0).to_numpy(float)
    med = ix.map(pair["median"]).fillna(fallback).to_numpy(float)
    return ((n * med + PAIR_PRIOR * category_prior) / (n + PAIR_PRIOR)).clip(1, 3)
