"""Backtest σε ψεύτικα cutoffs.

Δεν ξέρουμε το κρυφό απόθεμα του simulation, άρα η «αληθινή» εξάντληση στο backtest είναι proxy:
  truth ≈ ημερομηνία της επόμενης αγοράς μετά το cutoff (+ offset)
— ο πελάτης ξαναπαραγγέλνει όταν πλησιάζει στο μηδέν. Το proxy το βαθμονομούμε ώστε τα δύο σημεία αναφοράς του README
(«cutoff+30» ≈ 18,3 και «baseline 180 ημερών» ≈ 16,1) να βγαίνουν κοντά. Βλ. docs/RESULTS.md.

    uv run python -m forecast.backtest
"""
from __future__ import annotations

from typing import Callable

import pandas as pd

from .ingest import Data, load
from .score import score

# Ίδια εποχή με τον πραγματικό ορίζοντα (Νοε–Ιαν). Στο 2025-10-31/11-29 το baseline_180 δίνει ~16,1 όπως το README.
CUTOFFS = [pd.Timestamp(x) for x in ("2025-10-31", "2025-11-29", "2025-10-04")]

Model = Callable[[Data, pd.DataFrame, pd.DataFrame, pd.Timestamp], pd.DataFrame]


def history(d: Data, cutoff: pd.Timestamp) -> pd.DataFrame:
    if "in_promo" not in d.daily:
        from .models import promo_mask
        d.daily["in_promo"] = promo_mask(d, d.daily)
    return d.daily[d.daily["DATE"] <= cutoff]


def targets(d: Data, cutoff: pd.Timestamp) -> pd.DataFrame:
    """Ίδιος κανόνας με το prediction_targets.csv (επαληθευμένος: αναπαράγει ακριβώς τα 1.975 στο πραγματικό cutoff)."""
    h = history(d, cutoff)
    buys = h[h["gross"] > 0]
    g = buys.groupby(["TRDR", "MTRL"]).agg(n=("DATE", "nunique"), last=("DATE", "max")).reset_index()
    regular = g[(g["n"] >= 3) & (g["last"] >= cutoff - pd.Timedelta(days=120))]
    newest = d.customers.loc[(d.customers["INSDATE"] > cutoff - pd.Timedelta(days=90)) & (d.customers["INSDATE"] <= cutoff), "TRDR"]
    new_pairs = g[g["TRDR"].isin(newest)]
    out = pd.concat([regular, new_pairs])[["TRDR", "MTRL"]].drop_duplicates()
    # τα επίσημα targets δεν έχουν εποχικά είδη· τα βγάζουμε και από το backtest για να μοιάζει
    seasonal = set(d.items.loc[d.items["MTRCATEGORY"] == "Εποχικά", "MTRL"])
    return out[~out["MTRL"].isin(seasonal)].reset_index(drop=True)


def truth_next_purchase(d: Data, cutoff: pd.Timestamp, tg: pd.DataFrame, offset_days: float = 0.0) -> pd.DataFrame:
    end = cutoff + pd.Timedelta(days=90)
    fut = d.daily[(d.daily["DATE"] > cutoff) & (d.daily["DATE"] <= end) & (d.daily["gross"] > 0)]
    nxt = fut.groupby(["TRDR", "MTRL"], as_index=False)["DATE"].min()
    t = tg.merge(nxt, on=["TRDR", "MTRL"], how="left")
    t["DATE"] = t["DATE"] + pd.to_timedelta(offset_days, unit="D")
    return t


def run(models: dict[str, Model], d: Data | None = None, cutoffs=CUTOFFS, offset_days: float = 0.0) -> pd.DataFrame:
    d = d or load()
    rows = []
    for c in cutoffs:
        h, tg = history(d, c), targets(d, c)
        truth = truth_next_purchase(d, c, tg, offset_days)
        for name, fn in models.items():
            pred = fn(d, h, tg, c)
            rows.append({"cutoff": c.date(), "model": name, **score(pred, truth, c)})
    return pd.DataFrame(rows)


def summary(res: pd.DataFrame) -> pd.DataFrame:
    return res.groupby("model", sort=False)[["mae", "within_3", "within_7", "at_risk_precision", "at_risk_recall"]].mean().round(2)


if __name__ == "__main__":
    from .models import REGISTRY
    res = run(REGISTRY)
    print(res.to_string(index=False))
    print("\nmean over cutoffs\n", summary(res).to_string())
