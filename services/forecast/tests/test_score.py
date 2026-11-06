import pandas as pd

from forecast.score import score, pair_errors

C = pd.Timestamp("2026-10-31")
H = C + pd.Timedelta(days=90)  # 2027-01-29


def df(rows):
    return pd.DataFrame(rows, columns=["TRDR", "MTRL", "DATE"]).assign(DATE=lambda x: pd.to_datetime(x["DATE"]))


def test_readme_cases():
    truth = df([(1, 1, "2026-11-10"), (1, 2, None), (1, 3, None), (1, 4, "2026-12-01"), (1, 5, "2026-11-05")])
    pred = df([(1, 1, "2026-11-13"), (1, 2, None), (1, 3, "2027-01-19"), (1, 4, None)])  # (1,5) missing
    e = pair_errors(pred, truth, C).set_index("MTRL")["err"]
    assert e[1] == 3                       # abs diff
    assert e[2] == 0                       # both none
    assert e[3] == 10                      # horizon_end − pred
    assert e[4] == (H - pd.Timestamp("2026-12-01")).days
    assert e[5] == 60                      # missing


def test_prediction_beyond_horizon_counts_as_none():
    truth = df([(1, 1, None)])
    pred = df([(1, 1, "2027-02-15")])
    assert score(pred, truth, C)["mae"] == 0


def test_at_risk_precision_recall():
    truth = df([(1, 1, "2026-11-05"), (1, 2, "2026-11-30")])
    pred = df([(1, 1, "2026-11-06"), (1, 2, "2026-11-10")])
    s = score(pred, truth, C)
    assert s["at_risk_precision"] == 0.5 and s["at_risk_recall"] == 1.0


def test_submission_matches_template():
    from forecast.submit import build
    out = build()
    assert len(out) == 1975 and list(out.columns) == ["TRDR", "MTRL", "PREDICTED_DEPLETION_DATE", "SUGGESTED_QTY"]
    dates = pd.to_datetime(out["PREDICTED_DEPLETION_DATE"])
    assert (dates.dropna() > C).all() and (dates.dropna() < H).all()
    q = out["SUGGESTED_QTY"]
    assert q.notna().equals(dates.notna())          # ποσότητα μόνο όπου υπάρχει εξάντληση
    assert (q.dropna() >= 1).all() and (q.dropna() % 1 == 0).all()
