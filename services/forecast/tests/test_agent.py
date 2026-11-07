"""Agent: ανάγνωση από το ERP API (ίδια δεδομένα με τα CSV) και κανόνες ελέγχου των προτάσεων."""
import socket
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import pytest

from forecast import erp_source
from forecast.agent import priority_counts, validate_suggestion
from forecast.ingest import load

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def erp_url():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    p = subprocess.Popen([sys.executable, str(ROOT / "team_pack" / "mock_erp_server.py"), "--port", str(port)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            erp_source._get(url, "/api/salesmen", timeout=1); break
        except OSError:
            time.sleep(0.1)
    yield url
    p.terminate()


def test_erp_api_gives_same_data_as_csv(erp_url):
    a, b = load(), load(erp_source.fetch(erp_url))
    assert a.report == b.report
    cols = ["TRDR", "MTRL", "DATE", "qty", "gross", "returns"]
    assert a.daily[cols].reset_index(drop=True).equals(b.daily[cols].reset_index(drop=True))
    for k in ("customers", "items", "promos", "salesmen"):
        A, B = getattr(a, k), getattr(b, k)
        assert A.reset_index(drop=True).equals(B[A.columns].reset_index(drop=True)), k


def _sug(**over):
    s = {"TRDR": 1001, "SUGGESTED_DELIVERY_DATE": "2026-11-03", "urgency": "high",
         "LINES": [{"MTRL": 5001, "QTY1": 4, "PREDICTED_DEPLETION_DATE": "2026-11-06",
                    "evidence": {"last_purchase_date": "2026-10-01", "avg_interval_days": 14}}]}
    s.update(over); return s


WD = set(pd.bdate_range("2026-11-02", "2026-11-30")) | {pd.Timestamp("2026-11-07")}


def test_validate_rules():
    ok = lambda s: validate_suggestion(s, {1001}, {5001}, WD)
    assert ok(_sug()) == []
    assert any("εργάσιμη" in e for e in ok(_sug(SUGGESTED_DELIVERY_DATE="2026-11-08")))          # Κυριακή
    assert any("πριν την εξάντληση" in e for e in ok(_sug(SUGGESTED_DELIVERY_DATE="2026-11-06")))
    assert any("TRDR" in e for e in ok(_sug(TRDR=9)))
    bad = _sug(); bad["LINES"][0]["QTY1"] = 0
    assert any("QTY1" in e for e in ok(bad))


def test_priority_counts_match_dashboard_rule():
    # 30 μέρες χωρίς αγορά / κύκλος 14 = 2,1 κύκλοι → κρίσιμο· 50/14 = 3,6 → πιθανή απώλεια
    crit = _sug(); crit["LINES"][0]["evidence"]["last_purchase_date"] = "2026-10-01"
    lost = _sug(); lost["LINES"][0]["evidence"] = {"last_purchase_date": "2026-09-11", "avg_interval_days": 14}
    fine = _sug(); fine["LINES"][0]["evidence"]["last_purchase_date"] = "2026-10-25"
    pc = priority_counts([crit, lost, fine])
    assert (pc["critical"], pc["lost"], pc["high"]) == (1, 1, 1)
