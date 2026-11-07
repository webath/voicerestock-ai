"""Ingestion & cleaning: SALDOC (headers) + MTRLINES (lines) → καθαρές γραμμές και ημερήσιες ποσότητες.

Κανόνες (docs/DATA_NOTES.md):
  1. join MTRLINES.FINDOC = SALDOC.FINDOC (οι γραμμές δεν έχουν ημερομηνία/πελάτη)
  2. έξω τα ακυρωμένα headers (ISCANCEL=1) ΜΑΖΙ με τις γραμμές τους
  3. έξω οι υπηρεσίες (MTRL.MTRTYPE=1, π.χ. Μεταφορικά)
  4. πιστωτικά (SERIES=7071) → αρνητική ποσότητα
  5. free goods (PRICE=0) μένουν — παραδόθηκαν πραγματικά

    uv run python -m forecast.ingest      # γράφει data/processed/*.parquet + report
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "team_pack" / "data"
PROCESSED = ROOT / "data" / "processed"

CUTOFF = pd.Timestamp("2026-10-31")
HORIZON_END = pd.Timestamp("2027-01-29")
SERIES_INVOICE, SERIES_CREDIT = 7021, 7071


@dataclass
class Data:
    customers: pd.DataFrame
    items: pd.DataFrame
    salesmen: pd.DataFrame
    promos: pd.DataFrame
    holidays: pd.DataFrame
    targets: pd.DataFrame
    headers: pd.DataFrame
    lines: pd.DataFrame          # καθαρές γραμμές με στοιχεία header
    daily: pd.DataFrame          # (TRDR, MTRL, DATE) → qty (net), gross, returns
    report: list[tuple[str, int]] = field(default_factory=list)


def _csv(name: str) -> pd.DataFrame:
    return pd.read_csv(DATA / name, encoding="utf-8-sig")


def load_raw(erp_tables: dict[str, pd.DataFrame] | None = None) -> dict[str, pd.DataFrame]:
    """Πίνακες ERP από τα CSV του pack, ή (agent) από το ERP API — βλ. erp_source.fetch().
    Αργίες και prediction_targets δεν είναι δεδομένα ERP: έρχονται πάντα από το pack."""
    names = ("TRDR", "MTRL", "PRSN", "PROMO", "SALDOC", "MTRLINES")
    raw = {n: erp_tables[n].copy() for n in names} if erp_tables else {n: _csv(f"{n}.csv") for n in names}
    raw["holidays"] = _csv("greek_holidays.csv")
    raw["targets"] = _csv("prediction_targets.csv")
    for k, cols in {"TRDR": ["INSDATE"], "PROMO": ["FROMDATE", "TODATE"], "SALDOC": ["TRNDATE"], "holidays": ["DATE"]}.items():
        for c in cols:
            raw[k][c] = pd.to_datetime(raw[k][c])
    return raw


def clean(headers: pd.DataFrame, lines: pd.DataFrame, items: pd.DataFrame) -> tuple[pd.DataFrame, list[tuple[str, int]]]:
    rep: list[tuple[str, int]] = [("headers raw", len(headers)), ("lines raw", len(lines))]

    dup = headers["FINDOC"].duplicated().sum()
    if dup:
        raise ValueError(f"{dup} duplicate FINDOC in SALDOC")
    orphans = ~lines["FINDOC"].isin(headers["FINDOC"])
    rep.append(("orphan lines (no header)", int(orphans.sum())))
    unknown_series = set(headers["SERIES"]) - {SERIES_INVOICE, SERIES_CREDIT}
    if unknown_series:
        raise ValueError(f"unexpected SERIES: {unknown_series}")

    h_cols = ["FINDOC", "SERIES", "TRNDATE", "TRDR", "SALESMAN", "ISCANCEL"]
    df = lines[~orphans].merge(headers[h_cols], on="FINDOC", how="inner", validate="many_to_one")
    rep.append(("lines after join", len(df)))

    rep.append(("cancelled headers", int((headers["ISCANCEL"] == 1).sum())))
    df = df[df["ISCANCEL"] == 0]
    rep.append(("lines after dropping cancelled", len(df)))

    services = set(items.loc[items["MTRTYPE"] == 1, "MTRL"])
    rep.append(("service lines (MTRTYPE=1)", int(df["MTRL"].isin(services).sum())))
    df = df[~df["MTRL"].isin(services)].copy()
    rep.append(("lines after dropping services", len(df)))

    df["is_credit"] = df["SERIES"] == SERIES_CREDIT
    df["is_free"] = df["PRICE"] == 0
    df["signed_qty"] = df["QTY1"].where(~df["is_credit"], -df["QTY1"])
    rep += [("credit-note lines", int(df["is_credit"].sum())), ("free-goods lines kept", int(df["is_free"].sum()))]
    return df.drop(columns=["ISCANCEL"]).reset_index(drop=True), rep


def to_daily(lines: pd.DataFrame) -> pd.DataFrame:
    g = lines.assign(gross=lines["QTY1"].where(~lines["is_credit"], 0),
                     returns=lines["QTY1"].where(lines["is_credit"], 0))
    d = (g.groupby(["TRDR", "MTRL", "TRNDATE"], as_index=False)
          .agg(qty=("signed_qty", "sum"), gross=("gross", "sum"), returns=("returns", "sum")))
    return d.rename(columns={"TRNDATE": "DATE"}).sort_values(["TRDR", "MTRL", "DATE"]).reset_index(drop=True)


def load(erp_tables: dict[str, pd.DataFrame] | None = None) -> Data:
    raw = load_raw(erp_tables)
    lines, rep = clean(raw["SALDOC"], raw["MTRLINES"], raw["MTRL"])
    daily = to_daily(lines)
    rep.append(("daily (TRDR, MTRL, DATE) rows", len(daily)))
    return Data(customers=raw["TRDR"], items=raw["MTRL"], salesmen=raw["PRSN"], promos=raw["PROMO"],
                holidays=raw["holidays"], targets=raw["targets"], headers=raw["SALDOC"], lines=lines,
                daily=daily, report=rep)


def write_processed(d: Data) -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    d.lines.to_parquet(PROCESSED / "lines_clean.parquet", index=False)
    d.daily.to_parquet(PROCESSED / "daily.parquet", index=False)


def main() -> None:
    d = load()
    write_processed(d)
    print("Ingestion report")
    for k, v in d.report:
        print(f"  {k:<36} {v:>8,}")


if __name__ == "__main__":
    main()
