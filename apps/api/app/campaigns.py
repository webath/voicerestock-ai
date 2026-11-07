"""Campaigns: προσφορές, τιμές και ειδοποιήσεις κύκλου — ΜΟΝΟ από το ιστορικό τιμολογίων (κανένα LLM).

Τέσσερα κομμάτια, όλα με τα στοιχεία που τα στηρίζουν:
- seasonal: επόμενες γιορτές → ποια είδη ανεβαίνουν ιστορικά πριν από αυτές → σε ποιους πελάτες, με τι έκπτωση.
- pricing:  ζήτηση φέτος vs πέρυσι + ευαισθησία σε προσφορές + τελευταία αλλαγή τιμής → αύξηση / προσφορά / έλεγχος.
- alerts:   πελάτης × είδος όπου ο κύκλος αγορών «έσπασε» (πολύ περισσότερες μέρες από το συνηθισμένο).
- promos:   τι απέδωσαν οι προσφορές του PROMO.csv (πωλήσεις ανά μέρα στην προσφορά vs πριν).

Κάθε αριθμός βγαίνει από υπολογισμό εδώ· το UI και η Market Scan μόνο τους δείχνουν.
"""
from __future__ import annotations

from datetime import date, timedelta
from statistics import median

import pandas as pd

TODAY = date(2026, 11, 1)          # σενάριο: δεδομένα ως 31/10/2026 (ίδιο με lib/format.ts)
HORIZON_DAYS = 185                 # ως το Πάσχα 2027
PRE_DAYS, POST_DAYS = 14, 2        # παράθυρο γιορτής: δύο εβδομάδες πριν ως δύο μέρες μετά
BASE_FROM, BASE_TO = 70, 15        # βάση σύγκρισης: οι 8 εβδομάδες πριν το παράθυρο
MIN_UPLIFT, MIN_WINDOW_QTY = 1.25, 30
DEFAULT_DISC = 8                   # αν η κατηγορία δεν έχει ιστορικό προσφορών
MOVEABLE = {"Καθαρά Δευτέρα": -48, "Μεγάλη Παρασκευή": -2, "Κυριακή του Πάσχα": 0, "Δευτέρα του Πάσχα": 1,
            "Αγίου Πνεύματος": 50}
EVENT_OF = {"Μεγάλη Παρασκευή": "Πάσχα", "Κυριακή του Πάσχα": "Πάσχα", "Δευτέρα του Πάσχα": "Πάσχα",
            "Χριστούγεννα": "Χριστούγεννα", "Σύναξη της Θεοτόκου": "Χριστούγεννα"}


def pct_text(v: float) -> str:
    """+24% / −8% — ίδια στρογγυλοποίηση με το dashboard (Math.round)."""
    return f"{'+' if v > 0 else '−' if v < 0 else ''}{int(abs(v) * 100 + 0.5)}%"


def orthodox_easter(year: int) -> date:
    """Ορθόδοξο Πάσχα (αλγόριθμος Meeus, Ιουλιανό → Γρηγοριανό)."""
    a, b, c = year % 4, year % 7, year % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    month, day = divmod(d + e + 114, 31)
    return date(year, month, day + 1) + timedelta(days=13)


def _holidays(hol: pd.DataFrame) -> list[dict]:
    """Γιορτές του αρχείου + οι ίδιες για τον επόμενο χρόνο (σταθερές με ίδια ημερομηνία, κινητές από το Πάσχα)."""
    rows = [{"name": r.NAME, "date": pd.Timestamp(r.DATE).date()} for r in hol.itertuples()]
    known = {(r["name"], r["date"].year) for r in rows}
    last_year = max(r["date"].year for r in rows)
    for y in range(last_year + 1, TODAY.year + 2):
        for r in [r for r in rows if r["date"].year == last_year]:
            d = (orthodox_easter(y) + timedelta(days=MOVEABLE[r["name"]]) if r["name"] in MOVEABLE
                 else r["date"].replace(year=y))
            if (r["name"], y) not in known:
                rows.append({"name": r["name"], "date": d})
    return sorted(rows, key=lambda r: r["date"])


def _events(hol: pd.DataFrame) -> list[dict]:
    """Επόμενες γιορτές μέσα στον ορίζοντα, ομαδοποιημένες (Χριστούγεννα = 25+26/12, Πάσχα = Μ. Παρασκευή ως Δευτέρα)."""
    out: dict[tuple, dict] = {}
    for r in _holidays(hol):
        if not (TODAY <= r["date"] <= TODAY + timedelta(days=HORIZON_DAYS)):
            continue
        key = (EVENT_OF.get(r["name"], r["name"]), r["date"].year)
        ev = out.setdefault(key, {"name": key[0], "key": key[0], "date": r["date"], "end": r["date"], "days": []})
        ev["date"], ev["end"] = min(ev["date"], r["date"]), max(ev["end"], r["date"])
        ev["days"].append(r["name"])
    merged: list[dict] = []
    for ev in sorted(out.values(), key=lambda e: e["date"]):     # Πάσχα + Πρωτομαγιά κ.λπ. = μία καμπάνια
        if merged and (ev["date"] - merged[-1]["end"]).days <= 3:
            m = merged[-1]
            m["name"], m["end"], m["days"] = f"{m['name']} & {ev['name']}", max(m["end"], ev["end"]), m["days"] + ev["days"]
        else:
            merged.append(ev)
    return merged


def _past_dates(hol: pd.DataFrame, event: str, cutoff: date) -> list[date]:
    """Πότε έγινε η ίδια γιορτή στο παρελθόν (πρώτη μέρα της ομάδας), μόνο ως το τέλος των δεδομένων."""
    by_year: dict[int, date] = {}
    for r in _holidays(hol):
        if EVENT_OF.get(r["name"], r["name"]) == event and r["date"] + timedelta(days=POST_DAYS) <= cutoff:
            y = r["date"].year
            by_year[y] = min(by_year.get(y, r["date"]), r["date"])
    return sorted(by_year.values())


def _sum(daily: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    m = (daily["DATE"] >= pd.Timestamp(start)) & (daily["DATE"] <= pd.Timestamp(end))
    return daily.loc[m]


class Campaigns:
    def __init__(self, daily: pd.DataFrame, lines: pd.DataFrame, items: pd.DataFrame, customers: pd.DataFrame,
                 promos: pd.DataFrame, holidays: pd.DataFrame, salesmen: dict[int, str]):
        self.daily = daily.assign(DATE=pd.to_datetime(daily["DATE"]))
        self.lines = lines
        self.items = items.set_index("MTRL")
        self.customers = customers.set_index("TRDR")
        self.promos = promos
        self.holidays = holidays
        self.salesmen = salesmen
        self.cutoff = self.daily["DATE"].max().date()
        self._promo_stats = None

    # ---------- βοηθητικά ----------
    def _item(self, mtrl: int) -> dict:
        it = self.items.loc[mtrl]
        return {"MTRL": int(mtrl), "ITEM_NAME": it["NAME"], "CATEGORY": it["MTRCATEGORY"], "UNIT": it["MTRUNIT1"],
                "PRICE": float(it["PRICER"])}

    def _customer(self, trdr: int) -> dict:
        c = self.customers.loc[trdr]
        return {"TRDR": int(trdr), "CUSTOMER_NAME": c["NAME"], "CUSTOMER_CATEGORY": c["TRDCATEGORY"], "AREA": c["AREA"],
                "CITY": c["CITY"], "SALESMAN": int(c["SALESMAN"]), "SALESMAN_NAME": self.salesmen.get(int(c["SALESMAN"]))}

    def _active(self, days: int = 60) -> set[int]:
        return set(_sum(self.daily, self.cutoff - timedelta(days=days), self.cutoff)["TRDR"].unique())

    # ---------- προσφορές που έγιναν ----------
    def promo_stats(self) -> list[dict]:
        """Για κάθε προσφορά: πωλήσεις/μέρα των ειδών της στη διάρκειά της vs τις 6 εβδομάδες πριν."""
        if self._promo_stats is not None:
            return self._promo_stats
        out = []
        for p in self.promos.itertuples():
            start, end = pd.Timestamp(p.FROMDATE).date(), pd.Timestamp(p.TODATE).date()
            if end > self.cutoff:
                continue
            mtrls = ([int(p.MTRL)] if pd.notna(p.MTRL) else
                     [int(m) for m in self.items.index[self.items["MTRCATEGORY"] == p.MTRCATEGORY]])
            d = self.daily[self.daily["MTRL"].isin(mtrls)]
            during = _sum(d, start, end)["qty"].sum() / ((end - start).days + 1)
            before = _sum(d, start - timedelta(days=42), start - timedelta(days=1))["qty"].sum() / 42
            if before <= 0:
                continue
            cat = p.MTRCATEGORY if pd.notna(p.MTRCATEGORY) else self.items.loc[mtrls[0], "MTRCATEGORY"]
            out.append({"PROMO": int(p.PROMO), "NAME": p.NAME, "CATEGORY": cat, "FROM": str(start), "TO": str(end),
                        "DISC_PRC": float(p.DISC_PRC), "per_day_before": round(float(before), 1),
                        "per_day_during": round(float(during), 1), "uplift": round(float(during / before), 2)})
        self._promo_stats = sorted(out, key=lambda r: -r["uplift"])
        return self._promo_stats

    def category_response(self) -> dict[str, dict]:
        """Ανά κατηγορία: μέση άνοδος πωλήσεων στις προσφορές και η έκπτωση που απέδωσε καλύτερα."""
        by: dict[str, list[dict]] = {}
        for r in self.promo_stats():
            by.setdefault(r["CATEGORY"], []).append(r)
        out = {}
        for cat, rs in by.items():
            best = max(rs, key=lambda r: r["uplift"])
            out[cat] = {"promos": len(rs), "avg_uplift": round(float(sum(r["uplift"] for r in rs)) / len(rs), 2),
                        "best_disc": float(best["DISC_PRC"]), "best_uplift": float(best["uplift"])}
        return out

    def _scheduled(self, mtrl: int, start: date, end: date) -> str | None:
        cat = self.items.loc[mtrl, "MTRCATEGORY"]
        for p in self.promos.itertuples():
            f, t = pd.Timestamp(p.FROMDATE).date(), pd.Timestamp(p.TODATE).date()
            hits = (pd.notna(p.MTRL) and int(p.MTRL) == mtrl) or (pd.notna(p.MTRCATEGORY) and p.MTRCATEGORY == cat)
            if hits and f <= end and t >= start:
                return f"{p.NAME} ({f:%d/%m}–{t:%d/%m})"
        return None

    # ---------- εποχικές καμπάνιες ----------
    def seasonal(self) -> list[dict]:
        resp, active, out = self.category_response(), self._active(), []
        for ev in _events(self.holidays):
            past = _past_dates(self.holidays, ev["key"], self.cutoff)
            if not past:
                continue
            win = pre = 0
            per_item_win: dict[int, float] = {}
            per_item_base: dict[int, float] = {}
            buyers: dict[int, dict[int, float]] = {}
            for d in past:
                w = _sum(self.daily, d - timedelta(days=PRE_DAYS), d + timedelta(days=POST_DAYS))
                b = _sum(self.daily, d - timedelta(days=BASE_FROM), d - timedelta(days=BASE_TO))
                scale = (PRE_DAYS + POST_DAYS + 1) / (BASE_FROM - BASE_TO + 1)
                for m, q in w.groupby("MTRL")["qty"].sum().items():
                    per_item_win[m] = per_item_win.get(m, 0) + q
                for m, q in b.groupby("MTRL")["qty"].sum().items():
                    per_item_base[m] = per_item_base.get(m, 0) + q * scale
                for (m, t), q in w.groupby(["MTRL", "TRDR"])["qty"].sum().items():
                    buyers.setdefault(m, {})[t] = buyers.setdefault(m, {}).get(t, 0) + q
                win += w["qty"].sum()
                pre += b["qty"].sum() * scale
            items = []
            for m, wq in per_item_win.items():
                bq = per_item_base.get(m, 0)
                if wq < MIN_WINDOW_QTY or bq <= 0 or wq / bq < MIN_UPLIFT:
                    continue
                it = self._item(int(m))
                start, end = ev["date"] - timedelta(days=PRE_DAYS), ev["end"] + timedelta(days=POST_DAYS)
                r = resp.get(it["CATEGORY"])
                disc = r["best_disc"] if r else DEFAULT_DISC
                targets = sorted(((t, q) for t, q in buyers.get(m, {}).items() if t in active and q >= len(past)),
                                 key=lambda x: -x[1])[:8]
                items.append({
                    **it, "uplift": round(wq / bq, 2), "past_window_qty": int(wq / len(past)),
                    "past_years": [d.year for d in past],
                    "suggested_disc": disc,
                    "disc_basis": (f"η έκπτωση {r['best_disc']:g}% έφερε ×{r['best_uplift']:.2f} πωλήσεις σε προσφορά {it['CATEGORY']}"
                                   if r else "χωρίς ιστορικό προσφοράς στην κατηγορία — συνήθης έκπτωση"),
                    "promo_from": str(start), "promo_to": str(end),
                    "already_scheduled": self._scheduled(int(m), start, end),
                    "targets": [{**self._customer(int(t)), "past_qty": int(q / len(past))} for t, q in targets],
                })
            items.sort(key=lambda r: -(r["uplift"] * r["past_window_qty"]))
            if items:
                out.append({"event": ev["name"], "date": str(ev["date"]), "days_until": (ev["date"] - TODAY).days,
                            "holidays": ev["days"], "past_years": [d.year for d in past],
                            "total_uplift": round(win / pre, 2) if pre else None, "items": items[:6]})
        return out

    # ---------- τιμές ----------
    def pricing(self) -> list[dict]:
        resp = self.category_response()
        end = pd.Timestamp(self.cutoff)
        cur = _sum(self.daily, self.cutoff - timedelta(days=83), self.cutoff).groupby("MTRL")["qty"].sum()
        ly = _sum(self.daily, self.cutoff - timedelta(days=83 + 364), self.cutoff - timedelta(days=364)).groupby("MTRL")["qty"].sum()
        paid = self.lines[(~self.lines["is_free"]) & (~self.lines["is_credit"]) & (self.lines["PRICE"] > 0)]
        yoys = {m: cur.get(m, 0) / ly[m] - 1 for m in self.items.index
                if self.items.loc[m, "MTRTYPE"] != 1 and ly.get(m, 0) >= 20}
        typical = float(median(yoys.values())) if yoys else 0.0     # η εταιρεία μεγαλώνει· συγκρίνουμε με αυτό
        out = []
        for m, yoy in yoys.items():
            it = self._item(int(m))
            yoy = float(yoy)
            rel = yoy - typical
            hist = paid[paid["MTRL"] == m].groupby("PRICE")["TRNDATE"].min().sort_values()
            changes = [(float(p1), float(p2), d) for (p1, _), (p2, d) in zip(hist.items(), list(hist.items())[1:]) if p2 > 0]
            last_change = changes[-1] if changes else None
            yearly = [p2 / p1 - 1 for p1, p2, _ in changes if p1 > 0]
            months_since = round((end - last_change[2]).days / 30.4) if last_change else None
            r = resp.get(it["CATEGORY"])
            sens = r["avg_uplift"] if r else None
            base = {**it, "yoy": round(yoy, 3), "yoy_typical": round(typical, 3), "qty_12w": int(cur.get(m, 0)), "qty_12w_last_year": int(ly[m]),
                    "last_price_change_pct": round(yearly[-1], 3) if yearly else None,
                    "months_since_price_change": months_since, "promo_uplift": sens}
            if rel >= 0.07 and (months_since is None or months_since >= 9):
                pct = min(0.08, max(0.02, median(yearly))) if yearly else 0.03
                out.append({**base, "action": "increase", "change_pct": round(float(pct), 3),
                            "why": f"Η ζήτηση ανεβαίνει {pct_text(yoy)} σε σχέση με πέρυσι (ο κατάλογος συνολικά {pct_text(typical)}) "
                                   f"και η τιμή έχει να αλλάξει {months_since or '–'} μήνες· αύξηση όσο η συνήθης ετήσια."})
            elif rel <= -0.12 and sens is not None and sens >= 1.5:
                out.append({**base, "action": "promo", "change_pct": -r["best_disc"] / 100,
                            "why": f"Η ζήτηση {'πέφτει' if yoy < 0 else 'μένει πίσω'} ({pct_text(yoy)}, ο κατάλογος {pct_text(typical)}) και η κατηγορία ανταποκρίνεται σε προσφορές "
                                   f"(×{sens:.2f} κατά μέσο όρο) — προσφορά {r['best_disc']:g}% για ανάκαμψη."})
            elif rel <= -0.12:
                out.append({**base, "action": "review", "change_pct": None,
                            "why": f"Η ζήτηση μένει πίσω ({pct_text(yoy)}, ο κατάλογος {pct_text(typical)}) χωρίς να βοηθούν οι προσφορές — έλεγξε τιμή ανταγωνισμού "
                                   f"(καρτέλα Market Scan) πριν από έκπτωση."})
        order = {"increase": 0, "promo": 1, "review": 2}
        return sorted(out, key=lambda r: (order[r["action"]], -abs(r["yoy"] - typical)))

    # ---------- κύκλος που έσπασε ----------
    def alerts(self, min_ratio: float = 2.0) -> list[dict]:
        d = self.daily[self.daily["qty"] > 0].sort_values("DATE")
        last_year_window = _sum(d, TODAY - timedelta(days=364 + 45), TODAY - timedelta(days=364 - 30))
        seasonal_pairs = set(zip(last_year_window["TRDR"], last_year_window["MTRL"]))
        by_cust: dict[int, dict] = {}
        for (t, m), g in d.groupby(["TRDR", "MTRL"]):
            recent = g[g["DATE"] >= pd.Timestamp(TODAY - timedelta(days=365))]
            if len(g) < 4 or len(recent) < 3:     # μόνο όσα αγόραζε τακτικά τον τελευταίο χρόνο
                continue
            gaps = g["DATE"].diff().dt.days.dropna()
            cycle = float(gaps.median())
            since = (pd.Timestamp(TODAY) - g["DATE"].iloc[-1]).days
            if cycle <= 0 or since < 21 or since / cycle < min_ratio:
                continue
            if (t, m) not in seasonal_pairs:      # ούτε πέρυσι τέτοια εποχή → εποχικό κενό, όχι σήμα
                continue
            it = self._item(int(m))
            monthly = float(g["qty"].tail(6).mean()) * 30 / cycle * it["PRICE"]
            c = by_cust.setdefault(int(t), {**self._customer(int(t)), "items": [], "monthly_value": 0.0})
            c["items"].append({**it, "cycle_days": round(cycle), "days_since": since, "ratio": round(since / cycle, 1),
                               "last_purchase": str(g["DATE"].iloc[-1].date())})
            c["monthly_value"] += float(monthly)
        out = []
        for c in by_cust.values():
            c["items"].sort(key=lambda r: -r["ratio"])
            n = len(c["items"])
            all_quiet = (pd.Timestamp(TODAY) - d[d["TRDR"] == c["TRDR"]]["DATE"].max()).days
            worst = c["items"][0]["ratio"]
            lost = all_quiet >= 2 * min(i["cycle_days"] for i in c["items"])
            c.update({"monthly_value": round(c["monthly_value"]), "items_broken": n, "max_ratio": worst,
                      "days_since_any_purchase": all_quiet,
                      "severity": "high" if lost or worst >= 4 or c["monthly_value"] >= 500 else "medium",
                      "kind": "lost" if lost else "partial",
                      "action": ("Πιθανή απώλεια πελάτη: τηλεφώνημα από τον πωλητή και προσφορά επαναφοράς."
                                 if lost else
                                 f"Αγοράζει ακόμα, αλλά όχι {'αυτό το είδος' if n == 1 else f'αυτά τα {n} είδη'}: "
                                 "μάλλον τα παίρνει αλλού — πρόταση τιμής ή προσφορά στα συγκεκριμένα.")})
            out.append(c)
        return sorted(out, key=lambda c: (c["severity"] != "high", -c["monthly_value"]))

    # ---------- σύνοψη για την Market Scan ----------
    def internal_snapshot(self) -> dict:
        cur = _sum(self.daily, self.cutoff - timedelta(days=83), self.cutoff)
        ly = _sum(self.daily, self.cutoff - timedelta(days=83 + 364), self.cutoff - timedelta(days=364))
        cats = self.items["MTRCATEGORY"]
        c_now = cur.assign(CAT=cur["MTRL"].map(cats)).groupby("CAT")["qty"].sum()
        c_ly = ly.assign(CAT=ly["MTRL"].map(cats)).groupby("CAT")["qty"].sum()
        trend = {k: round(c_now.get(k, 0) / v - 1, 3) for k, v in c_ly.items() if v > 0}
        al = self.alerts()
        return {
            "data_until": str(self.cutoff),
            "category_trend_12w_vs_last_year": trend,
            "catalogue": [{"item": r["NAME"], "category": r["MTRCATEGORY"], "list_price_eur": float(r["PRICER"]),
                           "unit": r["MTRUNIT1"]} for _, r in self.items.reset_index().iterrows() if r["MTRTYPE"] != 1],
            "customer_types": self.customers["TRDCATEGORY"].value_counts().to_dict(),
            "areas": self.customers["AREA"].value_counts().to_dict(),
            "pricing_flags": [{"item": p["ITEM_NAME"], "action": p["action"], "yoy": p["yoy"]} for p in self.pricing()][:15],
            "broken_cycles": {"customers": len(al), "lost": sum(1 for a in al if a["kind"] == "lost"),
                              "top_items": pd.Series([i["ITEM_NAME"] for a in al for i in a["items"]]).value_counts()
                              .head(8).to_dict()},
            "promo_response_by_category": self.category_response(),
        }

    def report(self) -> dict:
        return {"today": str(TODAY), "data_until": str(self.cutoff), "seasonal": self.seasonal(),
                "pricing": self.pricing(), "alerts": self.alerts(), "promos": self.promo_stats(),
                "category_response": self.category_response()}
