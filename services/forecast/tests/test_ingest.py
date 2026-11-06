import numpy as np
import pandas as pd
import pytest

from forecast.ingest import load


@pytest.fixture(scope="module")
def d():
    return load()


def test_no_cancelled_quantities(d):
    cancelled = set(d.headers.loc[d.headers["ISCANCEL"] == 1, "FINDOC"])
    assert len(cancelled) == 362
    assert not d.lines["FINDOC"].isin(cancelled).any()


def test_credit_notes_are_negative(d):
    credit = d.lines[d.lines["SERIES"] == 7071]
    assert len(credit) > 0
    assert (credit["signed_qty"] < 0).all()
    assert (d.lines.loc[d.lines["SERIES"] == 7021, "signed_qty"] > 0).all()


def test_services_excluded(d):
    services = set(d.items.loc[d.items["MTRTYPE"] == 1, "MTRL"])
    assert services == {5081}
    assert not d.lines["MTRL"].isin(services).any()


def test_free_goods_kept(d):
    free = d.lines[d.lines["is_free"]]
    assert len(free) > 6000
    assert (free["signed_qty"] != 0).all()


def test_header_netamnt_matches_lines():
    # NETAMNT = Σ LINEVAL ανά παραστατικό (στα raw δεδομένα, μαζί με μεταφορικά)
    from forecast.ingest import load_raw
    raw = load_raw()
    s = raw["MTRLINES"].groupby("FINDOC")["LINEVAL"].sum().round(2)
    h = raw["SALDOC"].set_index("FINDOC")["NETAMNT"]
    assert np.allclose(h.loc[s.index], s, atol=0.02)


def test_daily_reconciles_with_lines(d):
    assert d.daily["qty"].sum() == pytest.approx(d.lines["signed_qty"].sum())
    assert not d.daily.duplicated(["TRDR", "MTRL", "DATE"]).any()


def test_no_deliveries_on_sundays(d):
    assert (pd.to_datetime(d.daily["DATE"]).dt.day_of_week != 6).all()
