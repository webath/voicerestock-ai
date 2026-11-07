"""Regression: το default μοντέλο πρέπει να μένει καλύτερο από το v2 και από τα σημεία αναφοράς (backtest σε ένα cutoff)."""
import pandas as pd
import pytest

from forecast.backtest import TRUTHS, history, run, targets, truth_next_purchase
from forecast.ingest import load
from forecast.models import DEFAULT_MODEL, REGISTRY


@pytest.fixture(scope="module")
def res():
    names = ["cutoff+30", "baseline_180", "hybrid_v2", DEFAULT_MODEL]
    return run({k: REGISTRY[k] for k in names}, load(), [pd.Timestamp("2025-10-31")], truth="calibrated").set_index("model")


def test_default_beats_v2_and_baselines(res):
    assert res.at[DEFAULT_MODEL, "mae"] < 3.5
    assert res.at[DEFAULT_MODEL, "mae"] < res.at["hybrid_v2", "mae"] - 1.5
    assert res.at[DEFAULT_MODEL, "within_7"] > 0.85


def test_calibrated_truth_matches_readme_anchors(res):
    # README: cutoff+30 ≈ 18,3 · baseline_180 ≈ 16,1 — το βαθμονομημένο truth πρέπει να τα πλησιάζει
    assert abs(res.at["cutoff+30", "mae"] - 18.3) < 1.5
    assert abs(res.at["baseline_180", "mae"] - 16.1) < 1.5


def test_calibrated_truth_is_after_next_purchase():
    d = load(); c = pd.Timestamp("2025-10-31"); tg = targets(d, c)
    t0 = truth_next_purchase(d, c, tg)
    t1 = truth_next_purchase(d, c, tg, *TRUTHS["calibrated"])
    delta = (t1["DATE"] - t0["DATE"]).dt.days.dropna()
    assert (delta >= 2).all() and delta.median() >= 3
    assert t0["DATE"].isna().equals(t1["DATE"].isna())
