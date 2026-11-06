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
    if CFG.get("promo_rate") and "in_promo" in h:
        w = h[(h["DATE"] > c - D(win)) & (h["DATE"] <= c)]
        np_qty = w[~w["in_promo"]].groupby(["TRDR", "MTRL"])["qty"].sum()
        promo_share = w.groupby(["TRDR", "MTRL"])["in_promo"].mean()     # ≈ μερίδιο αγορών σε προσφορά
        r_np = np_qty / (win * (1 - promo_share.clip(upper=0.8)))
        x["r_recent"] = r_np.reindex(x.index).fillna(x["r_recent"])
    x["r_ly_recent"] = _window_qty(h, c - D(365 + win), c - D(365)) / win
    x["r_ly_future"] = _window_qty(h, c - D(365), c - D(365 - 90)) / 90
    # ρυθμός «κύκλου»: ό,τι αγόρασε πριν την τελευταία αγορά / μέρες από την πρώτη ως την τελευταία (μέσα στο παράθυρο)
    b = h[(h["DATE"] > c - D(win)) & (h["DATE"] <= c) & (h["gross"] > 0)].sort_values("DATE")
    g = b.groupby(["TRDR", "MTRL"])
    span = (g["DATE"].max() - g["DATE"].min()).dt.days
    x["r_cycle"] = ((g["gross"].sum() - g["gross"].last()) / span.where(span > 0))
    x = x.reset_index()
    x[["r_recent", "r_ly_recent", "r_ly_future"]] = x[["r_recent", "r_ly_recent", "r_ly_future"]].fillna(0.0)
    return x


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


def promo_mask(d: Data, df: pd.DataFrame) -> pd.Series:
    """True για γραμμές (MTRL, DATE) που πέφτουν μέσα σε προσφορά του είδους ή της κατηγορίας του."""
    cat = df["MTRL"].map(d.items.set_index("MTRL")["MTRCATEGORY"])
    out = pd.Series(False, index=df.index)
    for p in d.promos.itertuples():
        hit = (df["MTRL"] == p.MTRL) if pd.notna(p.MTRL) else (cat == p.MTRCATEGORY)
        out |= hit & (df["DATE"] >= p.FROMDATE) & (df["DATE"] <= p.TODATE)
    return out


def _pair_intervals(h: pd.DataFrame, c: pd.Timestamp, days: int = 180) -> pd.DataFrame:
    buys = h[(h["gross"] > 0) & (h["DATE"] > c - pd.Timedelta(days=days))].sort_values("DATE")
    gap = buys.groupby(["TRDR", "MTRL"])["DATE"].diff().dt.days
    return gap.groupby([buys["TRDR"], buys["MTRL"]]).median().rename("interval").reset_index()


def peer_interval(d: Data, h: pd.DataFrame, tg: pd.DataFrame, c: pd.Timestamp) -> pd.Series:
    """Cold start: διάμεσο διάστημα αγορών του ίδιου είδους σε πελάτες ίδιου τύπου (fallback: όλοι οι πελάτες)."""
    iv = _pair_intervals(h, c).merge(d.customers[["TRDR", "TRDCATEGORY"]])
    by_type = iv.groupby(["TRDCATEGORY", "MTRL"])["interval"].median().rename("p1")
    by_item = iv.groupby("MTRL")["interval"].median().rename("p2")
    x = tg.merge(d.customers[["TRDR", "TRDCATEGORY"]], how="left")
    x = x.merge(by_type, left_on=["TRDCATEGORY", "MTRL"], right_index=True, how="left").merge(by_item, left_on="MTRL", right_index=True, how="left")
    return x["p1"].fillna(x["p2"]).fillna(14.0).values


# Ρυθμίσεις που αλλάζουν τα πειράματα (docs/RESULTS.md). Οι default είναι οι επικυρωμένες.
CFG = {"cold_rate": "cycle", "peer_cold_start": True,
       "qty_scaled_cadence": "promo", # "off" | "promo" (μόνο αν η τελευταία αγορά ήταν σε προσφορά) | "all"
       "promo_rate": False}           # ρυθμός χωρίς τις αγορές μέσα σε προσφορές   # "window": qty/90 μέρες · "cycle": ρυθμός κύκλου για ζεύγη χωρίς περσινό ιστορικό · "cycle_all": για όλα


def _yoy_frame(d: Data, h: pd.DataFrame, tg: pd.DataFrame, c: pd.Timestamp) -> pd.DataFrame:
    x = _rates(h, tg, c).merge(_last_buy(h), how="left")
    x["g_ratio"] = _group_season_ratio(d, h, tg, c).values
    x["has_ly"] = x["r_ly_recent"] > 0
    mode = CFG["cold_rate"]
    if mode in ("cycle", "cycle_all"):
        use = x["r_cycle"].notna() & ((~x["has_ly"]) if mode == "cycle" else True)
        x.loc[use, "r_recent"] = x.loc[use, "r_cycle"]
    x["peer_interval"] = peer_interval(d, h, tg, c)
    x["cold_pair"] = (~x["has_ly"]) & x["r_cycle"].isna()        # μία μόνο αγορά, χωρίς πέρσι
    if CFG["peer_cold_start"]:
        cp = x["cold_pair"] & x["last_qty"].notna()
        x.loc[cp, "r_recent"] = x.loc[cp, "last_qty"] / x.loc[cp, "peer_interval"]
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
    np_buys = buys[~buys["in_promo"]] if "in_promo" in buys else buys
    stats = pd.DataFrame({"interval": grp.median(), "interval_cv": grp.std() / grp.mean(),
                          "n_recent": buys.groupby(["TRDR", "MTRL"]).size(),
                          "qty_recent_median": buys.groupby(["TRDR", "MTRL"])["gross"].median(),
                          "qty_normal_median": np_buys.groupby(["TRDR", "MTRL"])["gross"].median(),
                          "qty_recent_max": buys.groupby(["TRDR", "MTRL"])["gross"].max()}).reset_index()
    last = buys.loc[buys.groupby(["TRDR", "MTRL"])["DATE"].idxmax()]
    lp = last.set_index(["TRDR", "MTRL"])["in_promo"].rename("last_in_promo") if "in_promo" in last else None
    x = tg.merge(stats, how="left").merge(_last_buy(h), how="left")
    x["last_in_promo"] = (x.set_index(["TRDR", "MTRL"]).index.map(lp).fillna(False).astype(bool)) if lp is not None else False
    if CFG["peer_cold_start"]:
        x["interval"] = x["interval"].fillna(pd.Series(peer_interval(d, h, tg, c), index=x.index))
    x["interval_used"] = x["interval"]
    mode = CFG["qty_scaled_cadence"]
    if mode != "off":
        scale = (x["last_qty"] / x["qty_normal_median"].fillna(x["qty_recent_median"])).clip(0.5, 3).fillna(1.0)
        apply = x["last_in_promo"] if mode == "promo" else pd.Series(True, index=x.index)
        x.loc[apply, "interval_used"] = x.loc[apply, "interval"] * scale[apply]
    x["DATE"] = x["last_date"] + pd.to_timedelta(np.ceil(x["interval_used"]), unit="D")
    x.loc[x["DATE"] <= c, "DATE"] = c + pd.Timedelta(days=1)
    return x


def cadence(d: Data, h: pd.DataFrame, tg: pd.DataFrame, c: pd.Timestamp) -> pd.DataFrame:
    """Επόμενη αγορά ≈ τελευταία αγορά + διάμεσο πρόσφατο διάστημα μεταξύ αγορών."""
    return _cadence_frame(d, h, tg, c)[["TRDR", "MTRL", "DATE"]]


def components(d: Data, h: pd.DataFrame, tg: pd.DataFrame, c: pd.Timestamp, w_cadence: float = 0.7) -> pd.DataFrame:
    """Όλα τα ενδιάμεσα του hybrid (για evidence / suggestions). Η στήλη DATE είναι η πρόβλεψη."""
    y = _yoy_frame(d, h, tg, c).rename(columns={"DATE": "date_yoy"})
    k = _cadence_frame(d, h, tg, c)[["TRDR", "MTRL", "DATE", "interval", "interval_used", "interval_cv", "n_recent",
                                      "qty_recent_median", "qty_recent_max", "last_in_promo"]].rename(columns={"DATE": "date_cadence"})
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
    "hybrid_0.7": hybrid(0.7),
}

DEFAULT_MODEL = "hybrid_0.7"
