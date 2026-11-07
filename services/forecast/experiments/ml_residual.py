"""Πείραμα (ΔΕΝ μπαίνει στο μοντέλο): gradient boosting που διορθώνει το λάθος του hybrid_v3. Βλ. docs/RESULTS.md («ML»).

Για κάθε cutoff αξιολόγησης εκπαιδεύεται ΜΟΝΟ σε cutoffs με cutoff + 90 ≤ cutoff αξιολόγησης (χωρίς διαρροή μέλλοντος).
Στόχος = βαθμονομημένο truth − πρόβλεψη v3, απώλεια απόλυτου λάθους (= MAE).

    uv run python experiments/ml_residual.py [cache_dir]     # ~5 λεπτά την πρώτη φορά (43 cutoffs), μετά από cache
"""
import sys, glob, os, warnings
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from forecast import models as M
from forecast.backtest import CUTOFFS, history, targets
from forecast.ingest import load

M.CFG["adaptive_promo"] = False  # το καταγεγραμμένο πείραμα αφορά το v3, όχι το default v4

warnings.filterwarnings("ignore")
CACHE = sys.argv[1] if len(sys.argv) > 1 else "data/processed/ml_cache"


def build_frame(cache: str) -> pd.DataFrame:
    os.makedirs(cache, exist_ok=True)
    cuts = list(pd.date_range("2025-02-01", "2026-08-01", freq="14D")) + list(CUTOFFS)
    d = None
    for c in cuts:
        f = f"{cache}/{c.date()}.parquet"
        if os.path.exists(f):
            continue
        d = d or load()
        h, tg = history(d, c), targets(d, c)
        x = M.components(d, h, tg, c)
        fut = d.daily[(d.daily.DATE > c) & (d.daily.DATE <= c + pd.Timedelta(days=90)) & (d.daily.gross > 0)]
        x = x.merge(fut.groupby(["TRDR", "MTRL"]).DATE.min().rename("next"), left_on=["TRDR", "MTRL"], right_index=True, how="left")
        x = x.merge(M._pair_intervals(h, c).rename(columns={"interval": "iv_truth"}), how="left")
        x = x.merge(d.customers[["TRDR", "TRDCATEGORY", "AREA"]], how="left").merge(d.items[["MTRL", "MTRCATEGORY"]], how="left")
        x.assign(c=c).to_parquet(f)
        print("cached", c.date(), flush=True)
    return pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(f"{cache}/*.parquet"))], ignore_index=True)


X = build_frame(CACHE)
c = X.c
X["pred"] = (X.DATE - c).dt.days.astype(float)                 # v3 (NaN = κενό)
X["kd"] = (X.date_cadence - c).dt.days.astype(float); X["yd"] = (X.date_yoy - c).dt.days.astype(float)
X["since"] = (c - X.last_date).dt.days.astype(float)
X["ratio"] = X.since / X.interval
X["seas"] = X.r_future / X.r_recent.where(X.r_recent > 0)
X["qratio"] = X.last_qty / X.qty_recent_median
X["month"] = c.dt.month
X["pred_month"] = ((c + pd.to_timedelta(X.pred.fillna(0), unit="D")).dt.month)
X["nd"] = (X.next - c).dt.days.astype(float)
for col in ["TRDCATEGORY", "MTRCATEGORY", "AREA"]: X[col] = X[col].astype("category")
X[["last_in_promo", "has_ly", "cold_pair"]] = X[["last_in_promo", "has_ly", "cold_pair"]].astype(float)
FEATS = ["pred", "kd", "yd", "interval", "interval_cv", "n_recent", "since", "ratio", "last_in_promo", "has_ly", "cold_pair",
         "r_recent", "r_future", "seas", "stock_c", "qratio", "g_ratio", "month", "pred_month", "TRDCATEGORY", "MTRCATEGORY", "AREA"]
FAM = {"cal": (2, .1), "T0": (0, 0), "+2": (2, 0), "+4": (4, 0), "F20": (0, .2), "M2": (1, .15)}
def truth(df, a, b): return df.nd + np.round(a + b * df.iv_truth.fillna(14))
def mae(p, t, H=90):
    p, t = np.asarray(p, float), np.asarray(t, float)
    pn = np.isnan(p) | (p >= H); tn = np.isnan(t) | (t >= H)
    e = np.where(~pn & ~tn, np.abs(p - t), 0.0); e = np.where(tn & ~pn, H - p, e); e = np.where(~tn & pn, H - t, e)
    return e.mean()
cuts = sorted(X.c.unique()); X["y"] = truth(X, *FAM["cal"]) - X.pred
def fit(train):
    tr = train[train.pred.notna() & train.y.notna() & (train.pred < 90) & (train.nd < 90)]
    m = HistGradientBoostingRegressor(loss="absolute_error", max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                                      min_samples_leaf=200, l2_regularization=1.0, categorical_features="from_dtype", random_state=0)
    return m.fit(tr[FEATS], tr.y), len(tr)
rows = []
evals = [e for e in cuts if pd.Timestamp(e) >= pd.Timestamp("2025-08-01")]
for E in evals:
    E = pd.Timestamp(E); train = X[X.c + pd.Timedelta(days=90) <= E]
    if train.c.nunique() < 6: continue
    m, n = fit(train); te = X[X.c == E].copy()
    corr = np.where(te.pred.notna(), m.predict(te[FEATS]), 0.0)
    r = {"cut": E.date(), "n_train_cuts": train.c.nunique(), "n_train": n}
    for lam in (0.5, 1.0):
        p = np.where(te.pred.isna(), np.nan, np.maximum(1, np.round(te.pred + lam * corr)))
        for k, ab in FAM.items(): r[f"{k}_ml{lam}"] = mae(p, truth(te, *ab))
    for k, ab in FAM.items(): r[f"{k}_base"] = mae(te.pred, truth(te, *ab))
    rows.append(r)
R = pd.DataFrame(rows); pd.set_option("display.width", 250)
print(R[["cut", "n_train_cuts", "cal_base", "cal_ml0.5", "cal_ml1.0", "T0_base", "T0_ml1.0", "+4_base", "+4_ml1.0", "F20_base", "F20_ml1.0"]].round(2).to_string(index=False))
seas = R[R.cut.astype(str).isin(["2025-10-04", "2025-10-31", "2025-11-29"])]
for name, g in (("ALL", R), ("SEASONAL", seas), ("2026 (more data)", R[R.cut.astype(str) >= "2026-01-01"])):
    print(f"\n{name} ({len(g)} cutoffs)")
    print(pd.DataFrame({k: [g[f"{k}_base"].mean(), g[f"{k}_ml0.5"].mean(), g[f"{k}_ml1.0"].mean()] for k in FAM}, index=["base", "ml×0.5", "ml×1"]).round(3).to_string())
    print("cutoffs where ml×1 worse than base (cal):", int((g["cal_ml1.0"] > g["cal_base"]).sum()), "/", len(g))
