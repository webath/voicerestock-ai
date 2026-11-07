"""VORA agent — ο κύκλος «τιμολόγια ERP → Suggested Orders», από άκρη σε άκρη, χωρίς άνθρωπο.

  1. fetch     διαβάζει τιμολόγια, πελάτες, είδη, προσφορές από το ERP API (fallback: CSV του pack)
  2. clean     ακυρωμένα, υπηρεσίες, πιστωτικά, free goods (ingest.clean)
  3. forecast  ημερομηνία εξάντλησης για τα 1.975 ζεύγη (hybrid_v4) + submission
  4. orders    Suggested Orders ανά πελάτη: ποσότητα, παράδοση σε εργάσιμη πριν την εξάντληση, evidence
  5. validate  κάθε πρόταση περνά από τους κανόνες του ERP (POST /api/draft-orders) και του README — πριν τη δει άνθρωπος
  6. selfcheck backtest: η ακρίβεια πρέπει να μείνει κάτω από το όριο, αλλιώς δεν δημοσιεύει
  7. publish   γράφει τα αρχεία που διαβάζουν το App API, το dashboard και ο voice agent (atomic)

Ο agent ΔΕΝ στέλνει μόνος του παραγγελίες στο ERP: τα drafts γίνονται μόνο αφού τα εγκρίνει ο πωλητής (dashboard ή φωνή).

    uv run python -m forecast.agent                    # από το ERP (ERP_BASE_URL, default http://localhost:8080)
    uv run python -m forecast.agent --source csv       # από τα CSV
    uv run python -m forecast.agent --jsonl            # γεγονότα ως JSON lines (τα διαβάζει το App API)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Callable

import pandas as pd

from . import erp_source
from .ingest import CUTOFF, PROCESSED, ROOT, Data, load, write_processed

MAE_LIMIT = 4.0          # αν το backtest ξεπεράσει αυτό, ο agent δεν δημοσιεύει (κάτι χάλασε στα δεδομένα)
RUNS_FILE = PROCESSED / "agent_runs.json"
KEEP_RUNS = 20

STEPS = [
    ("fetch", "Διάβασμα από το ERP"),
    ("clean", "Καθαρισμός τιμολογίων"),
    ("forecast", "Πρόβλεψη εξάντλησης"),
    ("orders", "Suggested Orders"),
    ("validate", "Έλεγχος με τους κανόνες του ERP"),
    ("selfcheck", "Αυτοέλεγχος ακρίβειας"),
    ("publish", "Δημοσίευση"),
]

Emit = Callable[[dict], None]


def _fmt(n: float) -> str:
    return f"{n:,.0f}".replace(",", ".")


# ---------- κανόνες ----------
def validate_suggestion(s: dict, trdr_ids: set[int], mtrl_ids: set[int], workdays: set[pd.Timestamp]) -> list[str]:
    """Ίδιοι έλεγχοι με το validate() του ERP (team_pack/mock_erp_server.py) + README §δ: παράδοση πριν την εξάντληση, εργάσιμη."""
    errs = []
    if s.get("TRDR") not in trdr_ids:
        errs.append(f"άγνωστος TRDR {s.get('TRDR')}")
    dd = str(s.get("SUGGESTED_DELIVERY_DATE", ""))
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", dd):
        errs.append("SUGGESTED_DELIVERY_DATE όχι YYYY-MM-DD")
    elif pd.Timestamp(dd) not in workdays:
        errs.append(f"παράδοση {dd} όχι εργάσιμη")
    lines = s.get("LINES") or []
    if not lines:
        errs.append("χωρίς γραμμές")
    for l in lines:
        if l.get("MTRL") not in mtrl_ids:
            errs.append(f"άγνωστο MTRL {l.get('MTRL')}")
        q = l.get("QTY1")
        if isinstance(q, bool) or not isinstance(q, (int, float)) or q <= 0:
            errs.append(f"MTRL {l.get('MTRL')}: QTY1 {q}")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", dd) and dd >= l.get("PREDICTED_DEPLETION_DATE", "9999"):
            errs.append(f"MTRL {l.get('MTRL')}: παράδοση {dd} όχι πριν την εξάντληση {l.get('PREDICTED_DEPLETION_DATE')}")
    return errs


def priority_counts(sugs: list[dict]) -> dict[str, int]:
    """Ίδιος κανόνας με το dashboard (apps/web/lib/priority.ts): κύκλοι χωρίς αγορά ≥1,5 → κρίσιμο, ≥3 → πιθανή απώλεια."""
    out = {"critical": 0, "high": 0, "lost": 0, "medium": 0, "low": 0}
    for s in sugs:
        r = 0.0
        for l in s["LINES"]:
            e = l.get("evidence") or {}
            if e.get("last_purchase_date") and e.get("avg_interval_days"):
                r = max(r, (CUTOFF - pd.Timestamp(e["last_purchase_date"])).days / e["avg_interval_days"])
        p = "lost" if r >= 3 else "critical" if s["urgency"] == "high" and r >= 1.5 else s["urgency"]
        out[p] += 1
    return out


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# ---------- κύκλος ----------
def run(source: str = "erp", erp_url: str = erp_source.ERP_URL, emit: Emit = lambda e: None, trigger: str = "manual") -> dict:
    from .submit import build as build_submission
    from .suggest import build as build_suggestions, evaluation_json, working_days

    rec = {"id": f"RUN-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}", "trigger": trigger,
           "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "source": source, "steps": [], "status": "running"}
    emit({"type": "run", **{k: rec[k] for k in ("id", "trigger", "started_at", "source")},
          "plan": [{"key": k, "label": l} for k, l in STEPS]})
    labels = dict(STEPS)

    def step(key: str, fn):
        t0 = time.time()
        emit({"type": "step", "key": key, "label": labels[key], "status": "running"})
        try:
            detail, metrics = fn()
            ev = {"type": "step", "key": key, "label": labels[key], "status": "done", "detail": detail,
                  "metrics": metrics, "ms": int((time.time() - t0) * 1000)}
        except Exception as e:  # noqa: BLE001 — κάθε αποτυχία καταγράφεται στο run
            ev = {"type": "step", "key": key, "label": labels[key], "status": "error", "detail": str(e),
                  "ms": int((time.time() - t0) * 1000)}
        rec["steps"].append(ev); emit(ev)
        if ev["status"] == "error":
            raise RuntimeError(ev["detail"])

    st: dict = {}
    try:
        def fetch():
            if source == "erp":
                try:
                    pages = []
                    tables = erp_source.fetch(erp_url, lambda p, n: (pages.append(p), emit(
                        {"type": "progress", "key": "fetch", "detail": f"σελίδα {p}/{n} τιμολογίων", "done": p, "total": n})))
                    st["tables"] = tables
                    return (f"{_fmt(len(tables['SALDOC']))} τιμολόγια ({_fmt(len(tables['MTRLINES']))} γραμμές) σε {len(pages)} σελίδες, "
                            f"{len(tables['TRDR'])} πελάτες, {len(tables['MTRL'])} είδη, {len(tables['PROMO'])} προσφορές · {erp_url}",
                            {"invoices": len(tables["SALDOC"]), "lines": len(tables["MTRLINES"]), "customers": len(tables["TRDR"]),
                             "items": len(tables["MTRL"]), "promotions": len(tables["PROMO"]), "pages": len(pages), "source": "erp"})
                except OSError as e:
                    rec["source"] = "csv"
                    emit({"type": "warning", "key": "fetch", "detail": f"Το ERP δεν απαντά ({e}) — διαβάζω τα CSV του pack"})
            st["tables"] = None
            return "από τα CSV του pack (team_pack/data)", {"source": "csv"}
        step("fetch", fetch)

        def clean():
            d: Data = load(st["tables"])
            st["d"] = d
            r = dict(d.report)
            return (f"{_fmt(r['cancelled headers'])} ακυρωμένα έξω, {_fmt(r['service lines (MTRTYPE=1)'])} γραμμές υπηρεσιών έξω, "
                    f"{_fmt(r['credit-note lines'])} πιστωτικά αφαιρούν ποσότητα, {_fmt(r['free-goods lines kept'])} δωρεάν μένουν",
                    {"cancelled": r["cancelled headers"], "service_lines": r["service lines (MTRTYPE=1)"],
                     "credit_lines": r["credit-note lines"], "free_lines": r["free-goods lines kept"], "daily_rows": len(d.daily)})
        step("clean", clean)

        def forecast():
            sub = build_submission(d=st["d"])
            st["sub"] = sub
            dated = sub["PREDICTED_DEPLETION_DATE"].notna()
            risk = (pd.to_datetime(sub["PREDICTED_DEPLETION_DATE"]) <= CUTOFF + pd.Timedelta(days=14)).sum()
            return (f"{_fmt(len(sub))} ζεύγη πελάτη × είδους: {_fmt(dated.sum())} με ημερομηνία, {_fmt((~dated).sum())} χωρίς εξάντληση "
                    f"σε 90 μέρες, {_fmt(risk)} At Risk ως 14/11",
                    {"pairs": len(sub), "with_date": int(dated.sum()), "blank": int((~dated).sum()), "at_risk": int(risk)})
        step("forecast", forecast)

        def orders():
            out = build_suggestions(st["d"])
            st["out"] = out
            s = out["suggestions"]
            price = st["d"].items.set_index("MTRL")["PRICER"].to_dict()
            value = sum(price.get(l["MTRL"], 0) * l["QTY1"] for x in s for l in x["LINES"])
            pc = priority_counts(s)
            return (f"{len(s)} προτάσεις, {sum(len(x['LINES']) for x in s)} γραμμές, {_fmt(value)} € · "
                    f"{pc['critical']} κρίσιμες, {pc['high']} επείγουσες, {pc['medium']} σύντομα, {pc['lost']} πιθανή απώλεια",
                    {"suggestions": len(s), "lines": sum(len(x["LINES"]) for x in s), "value_eur": round(value, 2), **pc})
        step("orders", orders)

        def validate():
            d = st["d"]
            wd = set(working_days(d))
            bad = {x["id"]: e for x in st["out"]["suggestions"]
                   if (e := validate_suggestion(x, set(d.customers["TRDR"]), set(d.items["MTRL"]), wd))}
            n = len(st["out"]["suggestions"])
            if bad:
                raise ValueError(f"{len(bad)}/{n} προτάσεις δεν περνούν: " + "; ".join(f"{k}: {v[0]}" for k, v in list(bad.items())[:3]))
            return (f"{n}/{n} περνούν: γνωστός πελάτης & είδη, ποσότητα > 0, παράδοση σε εργάσιμη και πριν την εξάντληση",
                    {"checked": n, "failed": 0})
        step("validate", validate)

        def selfcheck():
            ev = evaluation_json(st["d"], st["out"]["forecasts"])
            st["ev"] = ev
            rows = {r["model"]: r for r in ev["rows"]}
            m, b = rows[ev["default_model"]]["mae"], rows["baseline_180"]["mae"]
            if m > MAE_LIMIT:
                raise ValueError(f"backtest MAE {m:.2f} > όριο {MAE_LIMIT} — δεν δημοσιεύω")
            return (f"backtest: μέσο λάθος {m:.2f} μέρες (όριο {MAE_LIMIT}, baseline {b:.1f}) · εντός ±7: "
                    f"{rows[ev['default_model']]['within_7']:.0%}".replace(".", ","),
                    {"mae": m, "baseline_mae": b, "within_7": rows[ev["default_model"]]["within_7"], "limit": MAE_LIMIT})
        step("selfcheck", selfcheck)

        def publish():
            out = st["out"]
            write_processed(st["d"])
            dump = lambda name, obj: _atomic_write(PROCESSED / name, json.dumps(obj, ensure_ascii=False, indent=1))
            dump("forecasts.json", {"forecasts": out["forecasts"], "confidence_table": out["confidence_table"]})
            dump("evaluation.json", st["ev"])
            dump("suggestions.json", {"suggestions": out["suggestions"]})   # τελευταίο: το App API το βλέπει ως «νέο τρέξιμο»
            sub_path = ROOT / "submissions" / "team_voicerestock.csv"
            _atomic_write(sub_path, st["sub"].to_csv(index=False))
            return (f"suggestions.json, forecasts.json, evaluation.json, {sub_path.relative_to(ROOT)}",
                    {"files": 4})
        step("publish", publish)
        rec["status"] = "done"
    except RuntimeError:
        rec["status"] = "error"
    rec["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    rec["summary"] = {k: v for s in rec["steps"] if s["status"] == "done" for k, v in (s.get("metrics") or {}).items()}
    _save(rec)
    emit({"type": "end", "id": rec["id"], "status": rec["status"], "finished_at": rec["finished_at"]})
    return rec


def _save(rec: dict) -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    try:
        runs = json.loads(RUNS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        runs = []
    runs = [rec] + [r for r in runs if r.get("id") != rec["id"]]
    _atomic_write(RUNS_FILE, json.dumps(runs[:KEEP_RUNS], ensure_ascii=False, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["erp", "csv"], default="erp")
    ap.add_argument("--erp", default=erp_source.ERP_URL)
    ap.add_argument("--trigger", default="manual")
    ap.add_argument("--jsonl", action="store_true", help="γεγονότα ως JSON lines στο stdout")
    a = ap.parse_args()
    if a.jsonl:
        emit = lambda e: print(json.dumps(e, ensure_ascii=False), flush=True)
    else:
        def emit(e):
            if e["type"] == "step" and e["status"] != "running":
                mark = "✓" if e["status"] == "done" else "✗"
                print(f"{mark} {e['label']:<34} {e.get('detail', '')}  ({e.get('ms', 0)} ms)", flush=True)
            elif e["type"] == "warning":
                print(f"! {e['detail']}", flush=True)
    rec = run(a.source, a.erp, emit, a.trigger)
    sys.exit(0 if rec["status"] == "done" else 1)


if __name__ == "__main__":
    main()
