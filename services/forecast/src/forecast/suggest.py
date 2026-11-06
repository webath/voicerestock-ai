"""Suggested Orders + forecasts + evidence για το App API (σχήμα: docs/CONTRACTS.md).

    uv run python -m forecast.suggest      # γράφει data/processed/{suggestions,forecasts,evaluation}.json

Κανόνες:
- Γραμμή μπαίνει σε πρόταση αν η εξάντληση είναι ≤ cutoff + LOOKAHEAD_DAYS.
- Παράδοση: η τελευταία μέρα δρομολογίου του πελάτη πριν την πρώτη εξάντληση (εργάσιμη, όχι αργία, ≥ TODAY).
- Ποσότητα: κάλυψη κατανάλωσης ενός κύκλου αγορών (+10% ασφάλεια), όρια από τις πρόσφατες αγορές.
- Confidence: εμπειρικό P(|λάθος| ≤ 3 μέρες) στο backtest, ανά κατηγορία σταθερότητας κύκλου — ΟΧΙ από LLM.
"""
from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd

from .backtest import CUTOFFS, history, targets, truth_next_purchase
from .ingest import CUTOFF, PROCESSED, Data, load
from .models import DEFAULT_MODEL, components
from .score import pair_errors

TODAY = pd.Timestamp("2026-11-01")            # «Σήμερα είναι 1/11/2026» (README)
LOOKAHEAD_DAYS = 21
MODEL_VERSION = f"{DEFAULT_MODEL}@2026-11-06"
CV_BINS = [-np.inf, 0.15, 0.35, 0.6, np.inf]
CV_LABELS = ["πολύ σταθερός", "σταθερός", "μέτριος", "ασταθής"]


# ---------- ημερολόγιο ----------
def working_days(d: Data) -> pd.DatetimeIndex:
    hol = set(d.holidays.loc[d.holidays["TYPE"] == "PUBLIC_HOLIDAY", "DATE"])
    days = pd.date_range(TODAY, CUTOFF + pd.Timedelta(days=120))
    return pd.DatetimeIndex([x for x in days if x.day_of_week != 6 and x not in hol])


def route_weekdays(d: Data) -> dict[int, set[int]]:
    """Μέρες εβδομάδας που ο πελάτης παίρνει παραδόσεις (τελευταίες 120 μέρες, ≥15% των επισκέψεων)."""
    h = d.headers[(d.headers["ISCANCEL"] == 0) & (d.headers["TRNDATE"] > CUTOFF - pd.Timedelta(days=120))]
    wd = h.drop_duplicates(["TRDR", "TRNDATE"]).assign(w=lambda x: x["TRNDATE"].dt.day_of_week)
    share = wd.groupby("TRDR")["w"].value_counts(normalize=True)
    return {int(t): set(g.index.get_level_values(1)[g.values >= 0.15]) for t, g in share.groupby(level=0)}


def delivery_date(depletion: pd.Timestamp, routes: set[int], wdays: pd.DatetimeIndex) -> pd.Timestamp:
    ok = wdays[wdays < depletion]
    on_route = ok[[x.day_of_week in routes for x in ok]] if routes else ok
    if len(on_route):
        return on_route[-1]
    return ok[-1] if len(ok) else wdays[0]


# ---------- confidence ----------
def calibrate_confidence(d: Data) -> pd.Series:
    """P(|λάθος| ≤ 3) στο backtest ανά (σταθερότητα κύκλου, έχει πέρσι ιστορικό)."""
    rows = []
    for c in CUTOFFS:
        h, tg = history(d, c), targets(d, c)
        comp = components(d, h, tg, c)
        m = pair_errors(comp[["TRDR", "MTRL", "DATE"]], truth_next_purchase(d, c, tg), c)
        m["cv_bin"] = pd.cut(comp["interval_cv"].fillna(1.0), CV_BINS, labels=CV_LABELS).values
        m["has_ly"] = comp["has_ly"].values
        rows.append(m)
    m = pd.concat(rows)
    overall = (m["err"] <= 3).mean()
    g = m.groupby(["cv_bin", "has_ly"], observed=True)["err"].agg(hit=lambda e: (e <= 3).mean(), n="size")
    # μικρά δείγματα → συρρίκνωση προς τον συνολικό μέσο (n0 = 50)
    p = (g["hit"] * g["n"] + overall * 50) / (g["n"] + 50)
    return p.clip(0.3, 0.9).round(2)


# ---------- evidence ----------
def promos_for(d: Data, mtrl: int, start: pd.Timestamp, end: pd.Timestamp) -> list[dict]:
    cat = d.items.set_index("MTRL").at[mtrl, "MTRCATEGORY"]
    p = d.promos
    hit = p[((p["MTRL"] == mtrl) | (p["MTRCATEGORY"] == cat)) & (p["FROMDATE"] <= end) & (p["TODATE"] >= start)]
    return [{"name": r.NAME, "disc_prc": int(r.DISC_PRC), "from": r.FROMDATE.strftime("%Y-%m-%d"),
             "to": r.TODATE.strftime("%Y-%m-%d")} for r in hit.itertuples()]


def _r(x, n=2):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), n)


def evidence(d: Data, row, cold: bool, peer: str | None) -> dict:
    seasonal = row.r_future / row.r_recent if row.r_recent > 0 else None
    factors = []
    if seasonal is not None and abs(seasonal - 1) > 0.05 and row.r_future > 0:
        # πόσες μέρες αλλάζει η εξάντληση λόγω εποχής (με το ίδιο απόθεμα)
        impact = row.stock_c / row.r_future - row.stock_c / row.r_recent
        factors.append({"name": "seasonality", "impact_days": _r(impact, 1),
                        "source": "ίδια περίοδος πέρσι × φετινή τάση" if row.has_ly else "εποχικός δείκτης κατηγορίας × περιοχής"})
    if not math.isnan(row.interval):
        src = (f"αγοράζει κάθε ~{int(round(row.interval))} μέρες (διάμεσος 180 ημερών)" if not row.cold_pair
               else f"νέος πελάτης: κύκλος ~{int(round(row.interval))} μερών από παρόμοιους πελάτες")
        factors.append({"name": "purchase_cycle", "impact_days": None, "source": src})
    if row.last_in_promo and row.interval_used > row.interval:
        factors.append({"name": "promo_stockpile", "impact_days": _r(row.interval_used - row.interval, 1),
                        "source": "η τελευταία αγορά έγινε σε προσφορά με μεγαλύτερη ποσότητα από το συνηθισμένο — το απόθεμα κρατά περισσότερο"})
    warnings = []
    if cold:
        warnings.append("νέος πελάτης με λίγο ιστορικό")
    if not row.has_ly:
        warnings.append("χωρίς περσινό ιστορικό — εποχικότητα από παρόμοιους πελάτες")
    if row.cold_pair:
        warnings.append("μόνο μία αγορά — ο κύκλος εκτιμάται από παρόμοιους πελάτες")
    if pd.notna(row.interval_cv) and row.interval_cv > 0.6:
        warnings.append("ασταθής κύκλος αγορών")
    end = row.DATE if pd.notna(row.DATE) else CUTOFF + pd.Timedelta(days=90)
    promo = promos_for(d, row.MTRL, TODAY, end)
    return {
        "model_version": MODEL_VERSION,
        "burn_rate_per_day": _r(row.r_future, 3),
        "burn_rate_recent_per_day": _r(row.r_recent, 3),
        "last_purchase_date": row.last_date.strftime("%Y-%m-%d") if pd.notna(row.last_date) else None,
        "last_purchase_qty": int(row.last_qty) if pd.notna(row.last_qty) else None,
        "avg_interval_days": _r(row.interval, 1),
        "purchases_count": int(row.n_recent) if pd.notna(row.n_recent) else 0,
        "est_stock_at_cutoff": _r(row.stock_c, 1),
        "seasonal_multiplier": _r(seasonal, 2),
        "promo": promo[0] if promo else None,
        "cold_start": cold,
        "peer_group": peer,
        "factors": factors,
        "warnings": warnings,
    }


def quantity(row) -> tuple[int, int, int]:
    """(πρόταση, min, max) σε ακέραιες μονάδες MTRUNIT1."""
    cycle = row.interval if not math.isnan(row.interval) else 14
    need = row.r_future * cycle * 1.1
    med = row.qty_recent_median if pd.notna(row.qty_recent_median) else need
    qty = need if need > 0 else med
    qty = int(max(1, round(min(max(qty, 0.5 * med), 2 * med))))
    qmax = int(max(6, 3 * qty, (row.qty_recent_max or 0) * 2))
    return qty, 1, qmax


def urgency(days_left: int) -> str:
    return "high" if days_left <= 7 else "medium" if days_left <= 14 else "low"


# ---------- build ----------
def build(d: Data | None = None) -> dict:
    d = d or load()
    tmpl = d.targets[["TRDR", "MTRL"]]
    comp = components(d, history(d, CUTOFF), tmpl, CUTOFF)
    conf_table = calibrate_confidence(d)
    cust = d.customers.set_index("TRDR"); items = d.items.set_index("MTRL"); sm = d.salesmen.set_index("PRSN")
    wdays, routes = working_days(d), route_weekdays(d)

    comp["cv_bin"] = pd.cut(comp["interval_cv"].fillna(1.0), CV_BINS, labels=CV_LABELS)
    forecasts, by_customer = [], {}
    for r in comp.itertuples(index=False):
        c = cust.loc[r.TRDR]; it = items.loc[r.MTRL]
        cold = bool(c.INSDATE >= pd.Timestamp("2026-01-01"))
        conf = max(0.3, float(conf_table.get((r.cv_bin, r.has_ly), 0.4)) * (0.8 if cold else 1.0))
        days_left = int((r.DATE - CUTOFF).days) if pd.notna(r.DATE) else None
        fc = {"TRDR": int(r.TRDR), "MTRL": int(r.MTRL), "ITEM_NAME": it.NAME, "CATEGORY": it.MTRCATEGORY,
              "PREDICTED_DEPLETION_DATE": r.DATE.strftime("%Y-%m-%d") if days_left else None,
              "days_left": days_left, "CONFIDENCE": round(conf, 2),
              "urgency": urgency(days_left) if days_left else "none"}
        forecasts.append(fc)
        if days_left is None or days_left > LOOKAHEAD_DAYS:
            continue
        qty, qmin, qmax = quantity(r)
        peer = f"{c.TRDCATEGORY} / {c.AREA}" if (cold or not r.has_ly) else None
        line = {"MTRL": int(r.MTRL), "ITEM_CODE": it.CODE, "ITEM_NAME": it.NAME, "UNIT": it.MTRUNIT1,
                "QTY1": qty, "QTY_RECOMMENDED": qty, "QTY_MIN": qmin, "QTY_MAX": qmax,
                "PREDICTED_DEPLETION_DATE": fc["PREDICTED_DEPLETION_DATE"], "CONFIDENCE": fc["CONFIDENCE"],
                "evidence": evidence(d, r, cold, peer)}
        by_customer.setdefault(int(r.TRDR), []).append(line)

    suggestions = []
    for trdr, lines in by_customer.items():
        c = cust.loc[trdr]
        lines.sort(key=lambda l: l["PREDICTED_DEPLETION_DATE"])
        first = pd.Timestamp(lines[0]["PREDICTED_DEPLETION_DATE"])
        deliv = delivery_date(first, routes.get(trdr, set()), wdays)
        # στην ίδια παράδοση: ό,τι τελειώνει μέχρι μία εβδομάδα μετά την παράδοση
        lines = [l for l in lines if pd.Timestamp(l["PREDICTED_DEPLETION_DATE"]) <= deliv + pd.Timedelta(days=7)] or lines[:1]
        dd = lines[0]["PREDICTED_DEPLETION_DATE"]
        reason = (f"{lines[0]['ITEM_NAME']}: εκτιμώμενη εξάντληση {pd.Timestamp(dd):%d/%m}"
                  + (f" (+{len(lines) - 1} ακόμη είδη ως {pd.Timestamp(lines[-1]['PREDICTED_DEPLETION_DATE']):%d/%m})" if len(lines) > 1 else ""))
        suggestions.append({
            "id": f"SUG-{trdr}-001", "version": 1, "status": "proposed",
            "urgency": urgency(int((first - CUTOFF).days)),
            "TRDR": trdr, "CUSTOMER_CODE": c.CODE, "CUSTOMER_NAME": c.NAME, "CUSTOMER_CATEGORY": c.TRDCATEGORY,
            "AREA": c.AREA, "SALESMAN": int(c.SALESMAN), "SALESMAN_NAME": sm.at[int(c.SALESMAN), "NAME"],
            "SUGGESTED_DELIVERY_DATE": deliv.strftime("%Y-%m-%d"), "REASON": reason, "LINES": lines,
            "erp_draft_id": None, "updated_at": "2026-11-01T06:00:00Z",
        })
    order = {"high": 0, "medium": 1, "low": 2}
    suggestions.sort(key=lambda s: (order[s["urgency"]], s["LINES"][0]["PREDICTED_DEPLETION_DATE"]))
    return {"suggestions": suggestions, "forecasts": forecasts,
            "confidence_table": {f"{k[0]}|{'ly' if k[1] else 'no_ly'}": v for k, v in conf_table.items()}}


def evaluation_json(d: Data, forecasts: list[dict] | None = None) -> dict:
    from .backtest import run
    from .models import REGISTRY
    res = run(REGISTRY, d)
    n_date = sum(1 for f in forecasts or [] if f["PREDICTED_DEPLETION_DATE"])
    coverage = {"pairs": len(forecasts or []), "targets": int(len(d.targets)), "with_date": n_date,
                "blank": len(forecasts or []) - n_date}
    mean = res.groupby("model", sort=False)[["mae", "within_3", "within_7", "at_risk_precision", "at_risk_recall"]].mean().round(3)
    return {"source": "local_backtest (proxy truth = επόμενη αγορά· βλ. docs/RESULTS.md)",
            "cutoffs": [str(c.date()) for c in CUTOFFS], "default_model": DEFAULT_MODEL, "coverage": coverage,
            "readme_reference": {"cutoff+30": 18.3, "baseline_180": 16.1},
            "rows": [{"model": m, **{k: (None if pd.isna(v) else float(v)) for k, v in r.items()}} for m, r in mean.iterrows()],
            "per_cutoff": json.loads(res.assign(cutoff=res["cutoff"].astype(str)).to_json(orient="records"))}


def main() -> None:
    d = load()
    out = build(d)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    dump = lambda name, obj: (PROCESSED / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    dump("suggestions.json", {"suggestions": out["suggestions"]})
    dump("forecasts.json", {"forecasts": out["forecasts"], "confidence_table": out["confidence_table"]})
    dump("evaluation.json", evaluation_json(d, out["forecasts"]))
    s = out["suggestions"]
    print(f"{len(s)} suggestions, {sum(len(x['LINES']) for x in s)} lines; urgency:",
          pd.Series([x["urgency"] for x in s]).value_counts().to_dict())
    print("confidence table:", out["confidence_table"])


if __name__ == "__main__":
    main()
