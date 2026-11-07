"""Backtest σε ψεύτικα cutoffs.

Δεν ξέρουμε το κρυφό απόθεμα του simulation, άρα η «αληθινή» εξάντληση στο backtest είναι proxy:
  truth ≈ ημερομηνία της επόμενης αγοράς μετά το cutoff (+ λίγες μέρες «απόθεμα ασφαλείας», βλ. TRUTHS)
— ο πελάτης ξαναπαραγγέλνει όταν πλησιάζει στο μηδέν. Το proxy το βαθμονομούμε ώστε τα δύο σημεία αναφοράς του README
(«cutoff+30» ≈ 18,3 και «baseline 180 ημερών» ≈ 16,1) να βγαίνουν κοντά. Βλ. docs/RESULTS.md.

    uv run python -m forecast.backtest [-v] [--family]
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


# Παραλλαγές truth: (σταθερές μέρες, κλάσμα του κύκλου) μετά την επόμενη αγορά.
# «proxy» = σκέτη επόμενη αγορά. «calibrated» = +2 μέρες + 0,1 × κύκλος: με αυτό τα cutoff+30 / baseline_180 βγαίνουν
# ~18,5 / ~16,5 (README: 18,3 / 16,1), ενώ με το σκέτο proxy ~21,5 / ~14,9. Βλ. docs/RESULTS.md («Βαθμονόμηση truth»).
TRUTHS = {"proxy": (0.0, 0.0), "calibrated": (2.0, 0.1)}
# οικογένεια truths που ταιριάζουν εξίσου καλά στα anchors — για έλεγχο ευστάθειας
CALIBRATED_FAMILY = {"+2": (2.0, 0.0), "+4": (4.0, 0.0), "0,2·κύκλος": (0.0, 0.2), "+2+0,1·κύκλος": (2.0, 0.1), "+1+0,15·κύκλος": (1.0, 0.15)}


def truth_next_purchase(d: Data, cutoff: pd.Timestamp, tg: pd.DataFrame, offset_days: float = 0.0, frac: float = 0.0) -> pd.DataFrame:
    end = cutoff + pd.Timedelta(days=90)
    fut = d.daily[(d.daily["DATE"] > cutoff) & (d.daily["DATE"] <= end) & (d.daily["gross"] > 0)]
    nxt = fut.groupby(["TRDR", "MTRL"], as_index=False)["DATE"].min()
    t = tg.merge(nxt, on=["TRDR", "MTRL"], how="left")
    shift = pd.Series(offset_days, index=t.index, dtype=float)
    if frac:
        from .models import _pair_intervals
        iv = _pair_intervals(history(d, cutoff), cutoff)
        shift += frac * t.merge(iv, how="left")["interval"].fillna(14.0).values
    t["DATE"] = t["DATE"] + pd.to_timedelta(shift.round(), unit="D")
    return t


def run(models: dict[str, Model], d: Data | None = None, cutoffs=CUTOFFS, truth: str | tuple = "calibrated") -> pd.DataFrame:
    d = d or load()
    off, frac = TRUTHS[truth] if isinstance(truth, str) else truth
    rows = []
    for c in cutoffs:
        h, tg = history(d, c), targets(d, c)
        truth_df = truth_next_purchase(d, c, tg, off, frac)
        for name, fn in models.items():
            pred = fn(d, h, tg, c)
            rows.append({"cutoff": c.date(), "model": name, **score(pred, truth_df, c)})
    return pd.DataFrame(rows)


def summary(res: pd.DataFrame) -> pd.DataFrame:
    return res.groupby("model", sort=False)[["mae", "within_3", "within_7", "at_risk_precision", "at_risk_recall"]].mean().round(2)


if __name__ == "__main__":
    import sys
    from .models import REGISTRY
    d = load()
    for t in ("calibrated", "proxy"):
        res = run(REGISTRY, d, truth=t)
        if "-v" in sys.argv:
            print(res.to_string(index=False))
        print(f"\n[{t}] mean over cutoffs\n", summary(res).to_string())
    if "--family" in sys.argv:   # ευστάθεια σε όλη την οικογένεια βαθμονομημένων truths
        rows = {n: summary(run({k: REGISTRY[k] for k in ("cutoff+30", "baseline_180", "hybrid_v2", "hybrid_v3")}, d, truth=v))["mae"]
                for n, v in CALIBRATED_FAMILY.items()}
        print("\nMAE ανά βαθμονομημένο truth\n", pd.DataFrame(rows).to_string())
