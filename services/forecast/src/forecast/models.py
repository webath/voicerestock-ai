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


def seasonal_yoy(d: Data, h: pd.DataFrame, tg: pd.DataFrame, c: pd.Timestamp) -> pd.DataFrame:
    """Μελλοντικός ρυθμός = πέρσι την ίδια περίοδο × (φετινή/περσινή τάση)· fallback: εποχικός δείκτης ομάδας."""
    x = _rates(h, tg, c).merge(_last_buy(h), how="left")
    x["g_ratio"] = _group_season_ratio(d, h, tg, c).values
    has_ly = x["r_ly_recent"] > 0
    growth = (x["r_recent"] / x["r_ly_recent"].where(has_ly)).clip(0.3, 3)
    x["r_future"] = np.where(has_ly, x["r_ly_future"] * growth, x["r_recent"] * x["g_ratio"])
    x["DATE"] = _depletion(x, c, "r_recent", "r_future")
    return x[["TRDR", "MTRL", "DATE"]]


def seasonal_group(d: Data, h: pd.DataFrame, tg: pd.DataFrame, c: pd.Timestamp) -> pd.DataFrame:
    """Μελλοντικός ρυθμός = πρόσφατος ρυθμός × εποχικός δείκτης (κατηγορία × περιοχή)."""
    x = _rates(h, tg, c).merge(_last_buy(h), how="left")
    x["r_future"] = x["r_recent"] * _group_season_ratio(d, h, tg, c).values
    x["DATE"] = _depletion(x, c, "r_recent", "r_future")
    return x[["TRDR", "MTRL", "DATE"]]


def cadence(d: Data, h: pd.DataFrame, tg: pd.DataFrame, c: pd.Timestamp) -> pd.DataFrame:
    """Επόμενη αγορά ≈ τελευταία αγορά + διάμεσο πρόσφατο διάστημα μεταξύ αγορών."""
    buys = h[h["gross"] > 0].sort_values("DATE")
    buys = buys[buys["DATE"] > c - pd.Timedelta(days=180)]
    gap = buys.groupby(["TRDR", "MTRL"])["DATE"].diff().dt.days
    med = gap.groupby([buys["TRDR"], buys["MTRL"]]).median().rename("interval").reset_index()
    x = tg.merge(med, how="left").merge(_last_buy(h), how="left")
    x["DATE"] = x["last_date"] + pd.to_timedelta(x["interval"], unit="D")
    x.loc[x["DATE"] <= c, "DATE"] = c + pd.Timedelta(days=1)
    return x[["TRDR", "MTRL", "DATE"]]


REGISTRY = {
    "cutoff+30": cutoff_plus_30,
    "baseline_180": baseline_180,
    "seasonal_group": seasonal_group,
    "seasonal_yoy": seasonal_yoy,
    "cadence": cadence,
}
