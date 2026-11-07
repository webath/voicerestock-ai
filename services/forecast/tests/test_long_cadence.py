"""Το 365ήμερο ανακτά κύκλο από την παλιά σεζόν και παραμένει χρονικά απομονωμένο."""
import copy

import pandas as pd
import pytest

from forecast import models
from forecast.backtest import history, targets, run
from forecast.ingest import load


def test_long_cadence_recovers_sparse_recent_pair_without_changing_recent_stats():
    d = load(); c = pd.Timestamp("2026-04-04"); h, tg = history(d, c), targets(d, c)
    short = models.with_cfg(models.components, "short", cadence_days=180)(d, h, tg, c)
    long = models.components(d, h, tg, c)
    # Το lookback αφορά τον κύκλο, όχι πρόσφατες ποσότητες/ρυθμούς/confidence bins.
    for col in ["qty_recent_median", "qty_recent_max", "n_recent", "interval_cv", "r_recent", "r_future", "date_yoy"]:
        pd.testing.assert_series_equal(short[col], long[col])
    assert (short["interval"] != long["interval"]).any()
    assert models.CFG["cadence_days"] == 365


def test_full_v5_forecast_ignores_future_delivery_rows():
    d = load(); c = pd.Timestamp("2025-10-31"); tg = targets(d, c)
    old = models.REGISTRY["hybrid_v5"](d, history(d, c), tg, c)
    other = copy.copy(d)
    future = d.daily.iloc[:10].copy()
    future["DATE"] = c + pd.Timedelta(days=1)
    future["gross"] = 99999; future["qty"] = 99999
    other.daily = pd.concat([d.daily, future], ignore_index=True)
    new = models.REGISTRY["hybrid_v5"](other, history(other, c), tg, c)
    pd.testing.assert_frame_equal(old, new)


def test_v5_reduces_error_on_new_round_confirmation_periods():
    d = load()
    cuts = [pd.Timestamp(x) for x in ["2025-09-20", "2025-11-22", "2025-12-06", "2026-04-04", "2026-06-06", "2026-07-04"]]
    registry = {n: models.REGISTRY[n] for n in ["hybrid_v4", "hybrid_v5"]}
    for truth in ["calibrated", "proxy"]:
        result = run(registry, d, cuts, truth).groupby("model")["mae"].mean()
        assert result["hybrid_v5"] < result["hybrid_v4"] - 0.1
    assert models.CFG["cadence_days"] == 365  # οι παλιές εκδόσεις δεν αφήνουν αλλαγμένο global state
