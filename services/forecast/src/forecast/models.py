"""Μοντέλα πρόβλεψης ημερομηνίας εξάντλησης.

Κάθε μοντέλο: f(data, history ≤ cutoff, targets, cutoff) → DataFrame[TRDR, MTRL, DATE] (NaT = καμία εξάντληση).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .ingest import Data


def _last_buy(h: pd.DataFrame) -> pd.DataFrame:
    buys = h[h["gross"] > 0]
    idx = buys.groupby(["TRDR", "MTRL"])["DATE"].idxmax()
    return buys.loc[idx, ["TRDR", "MTRL", "DATE", "gross"]].rename(columns={"DATE": "last_date", "gross": "last_qty"})


def cutoff_plus_30(d: Data, h: pd.DataFrame, tg: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    return tg.assign(DATE=cutoff + pd.Timedelta(days=30))


def baseline_180(d: Data, h: pd.DataFrame, tg: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    """README baseline: μέσος ρυθμός 180 ημερών· απόθεμα = τελευταία παραλαβή − κατανάλωση από τότε."""
    w = h[h["DATE"] > cutoff - pd.Timedelta(days=180)]
    rate = (w.groupby(["TRDR", "MTRL"])["qty"].sum() / 180).rename("rate").reset_index()
    x = tg.merge(rate, how="left").merge(_last_buy(h), how="left")
    days = x["last_qty"] / x["rate"].where(x["rate"] > 0)
    x["DATE"] = x["last_date"] + pd.to_timedelta(np.ceil(days), unit="D")
    x.loc[x["DATE"] <= cutoff, "DATE"] = cutoff + pd.Timedelta(days=1)
    return x[["TRDR", "MTRL", "DATE"]]


def _window_qty(h: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    w = h[(h["DATE"] > start) & (h["DATE"] <= end)]
    return w.groupby(["TRDR", "MTRL"])["qty"].sum()


def _rates(h: pd.DataFrame, tg: pd.DataFrame, c: pd.Timestamp, win: int = 90) -> pd.DataFrame:
    D = lambda n: pd.Timedelta(days=n)
    x = tg.set_index(["TRDR", "MTRL"])
    x["r_recent"] = _window_qty(h, c - D(win), c) / win
    x["r_ly_recent"] = _window_qty(h, c - D(365 + win), c - D(365)) / win
    x["r_ly_future"] = _window_qty(h, c - D(365), c - D(365 - 90)) / 90
    return x.fillna(0.0).reset_index()


def _group_season_ratio(d: Data, h: pd.DataFrame, tg: pd.DataFrame, c: pd.Timestamp, win: int = 90) -> pd.Series:
    """Λόγος κατανάλωσης «επόμενες 90 μέρες / τελευταίες win μέρες» πέρσι, ανά (κατηγορία είδους × περιοχή)."""
    D = lambda n: pd.Timedelta(days=n)
    hh = h.merge(d.items[["MTRL", "MTRCATEGORY"]]).merge(d.customers[["TRDR", "AREA"]])
    def tot(a, b):
        w = hh[(hh["DATE"] > a) & (hh["DATE"] <= b)]
        return w.groupby(["MTRCATEGORY", "AREA"])["qty"].sum()
    ratio = (tot(c - D(365), c - D(275)) / 90) / (tot(c - D(365 + win), c - D(365)) / win)
    key = tg.merge(d.items[["MTRL", "MTRCATEGORY"]]).merge(d.customers[["TRDR", "AREA"]])
    return pd.Series(ratio.reindex(pd.MultiIndex.from_frame(key[["MTRCATEGORY", "AREA"]])).values, index=key.index).fillna(1.0)


def _depletion(x: pd.DataFrame, c: pd.Timestamp, rate_now: str, rate_future: str) -> pd.Series:
    """Απόθεμα = τελευταία παραλαβή − κατανάλωση ως το cutoff· μετά εξαντλείται με τον μελλοντικό ρυθμό."""
    since = (c - x["last_date"]).dt.days
    stock_c = x["last_qty"] - x[rate_now] * since
    rf = x[rate_future].where(x[rate_future] > 1e-6)
    days_after = (stock_c.clip(lower=0) / rf).clip(lower=1)
    out = c + pd.to_timedelta(np.ceil(days_after), unit="D")
    return out.where(rf.notna())


def _yoy_frame(d: Data, h: pd.DataFrame, tg: pd.DataFrame, c: pd.Timestamp) -> pd.DataFrame:
    x = _rates(h, tg, c).merge(_last_buy(h), how="left")
    x["g_ratio"] = _group_season_ratio(d, h, tg, c).values
    x["has_ly"] = x["r_ly_recent"] > 0
    growth = (x["r_recent"] / x["r_ly_recent"].where(x["has_ly"])).clip(0.3, 3)
    x["r_future"] = np.where(x["has_ly"], x["r_ly_future"] * growth, x["r_recent"] * x["g_ratio"])
    x["stock_c"] = (x["last_qty"] - x["r_recent"] * (c - x["last_date"]).dt.days).clip(lower=0)
    x["DATE"] = _depletion(x, c, "r_recent", "r_future")
    return x


def seasonal_yoy(d: Data, h: pd.DataFrame, tg: pd.DataFrame, c: pd.Timestamp) -> pd.DataFrame:
    """Μελλοντικός ρυθμός = πέρσι την ίδια περίοδο × (φετινή/περσινή τάση)· fallback: εποχικός δείκτης ομάδας."""
    return _yoy_frame(d, h, tg, c)[["TRDR", "MTRL", "DATE"]]


def seasonal_group(d: Data, h: pd.DataFrame, tg: pd.DataFrame, c: pd.Timestamp) -> pd.DataFrame:
    """Μελλοντικός ρυθμός = πρόσφατος ρυθμός × εποχικός δείκτης (κατηγορία × περιοχή)."""
    x = _rates(h, tg, c).merge(_last_buy(h), how="left")
    x["r_future"] = x["r_recent"] * _group_season_ratio(d, h, tg, c).values
    x["DATE"] = _depletion(x, c, "r_recent", "r_future")
    return x[["TRDR", "MTRL", "DATE"]]


def _cadence_frame(d: Data, h: pd.DataFrame, tg: pd.DataFrame, c: pd.Timestamp) -> pd.DataFrame:
    buys = h[h["gross"] > 0].sort_values("DATE")
    buys = buys[buys["DATE"] > c - pd.Timedelta(days=180)]
    gap = buys.groupby(["TRDR", "MTRL"])["DATE"].diff().dt.days
    grp = gap.groupby([buys["TRDR"], buys["MTRL"]])
    stats = pd.DataFrame({"interval": grp.median(), "interval_cv": grp.std() / grp.mean(),
                          "n_recent": buys.groupby(["TRDR", "MTRL"]).size(),
                          "qty_recent_median": buys.groupby(["TRDR", "MTRL"])["gross"].median(),
                          "qty_recent_max": buys.groupby(["TRDR", "MTRL"])["gross"].max()}).reset_index()
    x = tg.merge(stats, how="left").merge(_last_buy(h), how="left")
    x["DATE"] = x["last_date"] + pd.to_timedelta(np.ceil(x["interval"]), unit="D")
    x.loc[x["DATE"] <= c, "DATE"] = c + pd.Timedelta(days=1)
    return x


def cadence(d: Data, h: pd.DataFrame, tg: pd.DataFrame, c: pd.Timestamp) -> pd.DataFrame:
    """Επόμενη αγορά ≈ τελευταία αγορά + διάμεσο πρόσφατο διάστημα μεταξύ αγορών."""
    return _cadence_frame(d, h, tg, c)[["TRDR", "MTRL", "DATE"]]


def components(d: Data, h: pd.DataFrame, tg: pd.DataFrame, c: pd.Timestamp, w_cadence: float = 0.6) -> pd.DataFrame:
    """Όλα τα ενδιάμεσα του hybrid (για evidence / suggestions). Η στήλη DATE είναι η πρόβλεψη."""
    y = _yoy_frame(d, h, tg, c).rename(columns={"DATE": "date_yoy"})
    k = _cadence_frame(d, h, tg, c)[["TRDR", "MTRL", "DATE", "interval", "interval_cv", "n_recent",
                                      "qty_recent_median", "qty_recent_max"]].rename(columns={"DATE": "date_cadence"})
    x = y.merge(k, on=["TRDR", "MTRL"], how="left")
    yd = (x["date_yoy"] - c).dt.days
    kd = (x["date_cadence"] - c).dt.days.fillna(yd)
    days = (w_cadence * kd + (1 - w_cadence) * yd).round().clip(lower=1)
    x["DATE"] = (c + pd.to_timedelta(days, unit="D")).where(x["date_yoy"].notna())
    return x


def hybrid(w_cadence: float = 0.5):
    """«Καμία εξάντληση» από το seasonal_yoy (πιάνει τα ζεύγη που σταματούν τον χειμώνα)·
    ημερομηνία = σταθμισμένος μέσος cadence και seasonal_yoy."""
    def f(d: Data, h: pd.DataFrame, tg: pd.DataFrame, c: pd.Timestamp) -> pd.DataFrame:
        return components(d, h, tg, c, w_cadence)[["TRDR", "MTRL", "DATE"]]
    f.__name__ = f"hybrid_{w_cadence}"
    return f


REGISTRY = {
    "cutoff+30": cutoff_plus_30,
    "baseline_180": baseline_180,
    "seasonal_group": seasonal_group,
    "seasonal_yoy": seasonal_yoy,
    "cadence": cadence,
    "hybrid_0.6": hybrid(0.6),
}

DEFAULT_MODEL = "hybrid_0.6"
