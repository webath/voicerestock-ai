"""Αναπαραγώγιμη σύγκριση v3/v4/v5. Δεν γράφει submission ή runtime δεδομένα.

    uv run python experiments/validate_adaptive_promo.py --output experiments/results/cadence_365.csv

Οι 3 development ημερομηνίες ήταν ήδη στο project. Άλλες 8 χρησιμοποιήθηκαν για screening
περιορισμένων υποψηφίων. Οι 6 confirmation ημερομηνίες αξιολογήθηκαν αφού επιλέχθηκε η μέθοδος.
Άλλες 6 confirmation_v5 ημερομηνίες ελέγχουν τον δεύτερο γύρο (κύκλος 365 ημερών).
Όλες έχουν πλήρη ορίζοντα 90 ημερών. Το truth παραμένει proxy, όχι φυσική απογραφή.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from forecast.backtest import CALIBRATED_FAMILY, CUTOFFS, history, targets, truth_next_purchase
from forecast.ingest import load
from forecast.models import REGISTRY
from forecast.score import pair_errors, score

SPLITS = {
    "development": [str(c.date()) for c in CUTOFFS],
    "screening": ["2025-09-13", "2025-10-18", "2025-11-15", "2025-12-13", "2026-03-14", "2026-05-16", "2026-07-18", "2026-08-01"],
    "confirmation": ["2025-09-27", "2025-11-08", "2025-12-20", "2026-04-18", "2026-06-20", "2026-08-02"],
    "confirmation_v5": ["2025-09-20", "2025-11-22", "2025-12-06", "2026-04-04", "2026-06-06", "2026-07-04"],
}
TRUTHS = {"calibrated": (2.0, 0.1), "proxy": (0.0, 0.0), **CALIBRATED_FAMILY}


def evaluate(phase: str = "all") -> tuple[pd.DataFrame, pd.DataFrame]:
    d = load()
    rows, errors = [], []
    for split, cuts in SPLITS.items():
        if phase != "all" and phase != split:
            continue
        for cut in cuts:
            c = pd.Timestamp(cut)
            assert c + pd.Timedelta(days=90) <= d.daily["DATE"].max(), "incomplete truth horizon"
            h, tg = history(d, c), targets(d, c)
            preds = {name: REGISTRY[name](d, h, tg, c) for name in ("hybrid_v3", "hybrid_v4", "hybrid_v5")}
            for truth, ab in TRUTHS.items():
                t = truth_next_purchase(d, c, tg, *ab)
                for name, p in preds.items():
                    rows.append({"split": split, "cutoff": cut, "truth": truth, "model": name, **score(p, t, c)})
                if split in {"confirmation", "confirmation_v5"} and truth == "calibrated":
                    a, b = ("hybrid_v3", "hybrid_v4") if split == "confirmation" else ("hybrid_v4", "hybrid_v5")
                    old = pair_errors(preds[a], t, c)
                    new = pair_errors(preds[b], t, c)
                    assert old[["TRDR", "MTRL"]].equals(new[["TRDR", "MTRL"]])
                    errors.append(pd.DataFrame({"comparison": f"{a} → {b}", "TRDR": old["TRDR"], "cutoff": cut, "delta": old["err"] - new["err"], "n": 1}))
            print(f"{split}: {cut}", flush=True)
    return pd.DataFrame(rows), pd.concat(errors, ignore_index=True) if errors else pd.DataFrame()


def customer_bootstrap(errors: pd.DataFrame, samples: int = 10000) -> tuple[float, float]:
    """Ο ίδιος πελάτης επαναδειγματοληπτείται μαζί σε όλα τα cutoffs. Δείκτης = μέσος MAE ανά cutoff."""
    grouped = errors.groupby(["TRDR", "cutoff"])[["delta", "n"]].sum()
    delta = grouped["delta"].unstack(fill_value=0).to_numpy(float)
    counts = grouped["n"].unstack(fill_value=0).to_numpy(float)
    rng = np.random.default_rng(20261107)
    ix = rng.integers(0, len(delta), (samples, len(delta)))
    gains = (delta[ix].sum(axis=1) / counts[ix].sum(axis=1)).mean(axis=1)
    return tuple(np.quantile(gains, [0.025, 0.975]))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase", choices=["all", *SPLITS], default="all")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    results, errors = evaluate(args.phase)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        results.to_csv(args.output, index=False)
    print(results.pivot_table(index=["split", "model"], columns="truth", values="mae").round(4).to_string())
    print(results[results.truth == "calibrated"].pivot(index="cutoff", columns="model", values="mae").to_string())
    if not errors.empty:
        for comparison, group in errors.groupby("comparison"):
            print(comparison, "95% customer-cluster bootstrap CI, MAE reduction (days):", customer_bootstrap(group))


if __name__ == "__main__":
    main()
