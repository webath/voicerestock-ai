"""Adaptive promo: temporal isolation, shrinkage, alignment and comparison with frozen v3."""
import numpy as np
import pandas as pd
import pytest

from forecast.promo import adaptive_promo_multiplier
from forecast import models
from forecast.backtest import CUTOFFS, history, run, targets
from forecast.ingest import load


def sample():
    h = pd.DataFrame({"TRDR": [1, 1, 1], "MTRL": [10, 10, 10], "gross": [5, 5, 5],
                      "DATE": pd.to_datetime(["2025-01-01", "2025-01-15", "2025-01-29"]),
                      "in_promo": [True, False, True]})
    items = pd.DataFrame({"MTRL": [10, 11, 20], "MTRCATEGORY": ["water", "water", "coffee"]})
    iv = pd.DataFrame({"TRDR": [1], "MTRL": [10], "interval": [7.0]})
    tg = pd.DataFrame({"TRDR": [1, 2, 3], "MTRL": [10, 11, 20]}, index=[8, 2, 4])
    return h, items, iv, tg, pd.Timestamp("2025-02-01")


def test_hierarchical_shrinkage_and_target_order():
    h, items, iv, tg, c = sample()
    mult = adaptive_promo_multiplier(h, items, iv, tg, c)
    category = (2 + 30 * 1.8) / 31
    assert mult == pytest.approx([(2 + 5 * category) / 6, category, 1.8])
    order = [2, 0, 1]
    assert adaptive_promo_multiplier(h, items, iv, tg.iloc[order], c) == pytest.approx(mult[order])


def test_future_orders_and_unfinished_gap_do_not_train_multiplier():
    h, items, iv, tg, c = sample()
    before = adaptive_promo_multiplier(h, items, iv, tg, c)
    # Last promo at 29/1 has no known successor at the cutoff. An order in March is invisible.
    future = h.iloc[[0]].assign(DATE=pd.Timestamp("2025-03-01"), gross=10000)
    assert adaptive_promo_multiplier(pd.concat([h, future]), items, iv, tg, c) == pytest.approx(before)
    assert adaptive_promo_multiplier(h.iloc[[2]], items, iv, tg, c) == pytest.approx([1.8] * 3)


def test_no_history_and_invalid_intervals_fall_back():
    h, items, iv, tg, c = sample()
    assert adaptive_promo_multiplier(h.iloc[:0], items, iv, tg, c) == pytest.approx([1.8] * 3)
    for invalid in [0.0, np.nan]:
        assert adaptive_promo_multiplier(h, items, iv.assign(interval=invalid), tg, c) == pytest.approx([1.8] * 3)


def test_v3_is_frozen_and_v4_does_not_change_regular_purchase_cycles():
    d = load(); c = pd.Timestamp("2025-10-31"); h, tg = history(d, c), targets(d, c)
    before = dict(models.CFG)
    v3 = models.REGISTRY["hybrid_v3"](d, h, tg, c)
    assert models.CFG == before
    old = models.CFG["adaptive_promo"]
    try:
        models.CFG["adaptive_promo"] = False
        legacy = models.components(d, h, tg, c)
    finally:
        models.CFG["adaptive_promo"] = old
    pd.testing.assert_frame_equal(v3, legacy[["TRDR", "MTRL", "DATE"]])
    newer = models.components(d, h, tg, c)
    regular = ~newer["last_in_promo"]
    pd.testing.assert_series_equal(newer.loc[regular, "DATE"], legacy.loc[regular, "DATE"])
    assert newer["promo_cycle_multiplier"].between(1, 3).all()


def test_v4_improves_development_and_additional_confirmation_dates():
    d = load()
    confirm = [pd.Timestamp(x) for x in ["2025-09-27", "2025-11-08", "2025-12-20", "2026-04-18", "2026-06-20", "2026-08-02"]]
    registry = {n: models.REGISTRY[n] for n in ["hybrid_v3", "hybrid_v4"]}
    for cuts in (CUTOFFS, confirm):
        for truth in ("calibrated", "proxy"):
            result = run(registry, d, cuts, truth).groupby("model")["mae"].mean()
            assert result["hybrid_v4"] < result["hybrid_v3"] - 0.02
