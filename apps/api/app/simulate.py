"""Προσομοίωση κλήσης VORA για το demo — χωρίς τηλέφωνο, χωρίς VPS.

Ένα κουμπί στο dashboard (σελίδα «Κλήσεις») → POST /api/calls/simulate. Εδώ «παίζεται» μια κλήση του AI βοηθού
στον πωλητή για τον πιο επείγοντα at-risk πελάτη του (ίδια σειρά με το dashboard και τον πραγματικό voice agent):
εξήγηση μόνο από το evidence, αλλαγή ποσότητας, ακριβής περίληψη, «ναι, επιβεβαιώνω», draft στο ERP.

Δεν είναι «ψεύτικο» από τη μέση και πέρα: η αλλαγή ποσότητας, η επιβεβαίωση και το draft περνούν από τα ίδια
endpoints με τους ίδιους κανόνες (version, confirmation token, idempotency key). Μόνο οι ατάκες του πωλητή είναι
γραμμένες. Τα γεγονότα γράφονται με το ίδιο schema που στέλνει ο πραγματικός voice agent (/api/calls/events),
οπότε η κάρτα της κλήσης στο dashboard είναι ίδια· το call_sid ξεκινά με «SIM-».
"""
from __future__ import annotations

import logging
import os
import secrets
import threading
import time
from datetime import date
from typing import Callable

CUTOFF = date(2026, 10, 31)
CRITICAL_RATIO, LOST_RATIO = 1.5, 3.0          # ίδια όρια με apps/web/lib/priority.ts
PRIORITY_ORDER = {"critical": 0, "high": 1, "lost": 2, "medium": 3, "low": 4}
OPEN = ("proposed", "modified")
WEEKDAYS = ("Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη", "Παρασκευή", "Σάββατο", "Κυριακή")
UNITS = {"ΚΙΒ": ("κιβώτιο", "κιβώτια"), "ΤΕΜ": ("τεμάχιο", "τεμάχια")}
log = logging.getLogger("simulate")


class NoSuggestion(Exception):
    pass


class Busy(Exception):
    pass


# ---------------- προτεραιότητα (όπως priority.ts / vr_core.priority_of) ----------------
def _d(iso: str) -> date:
    return date.fromisoformat(iso[:10])


def worst_line(s: dict) -> tuple[dict | None, float | None]:
    """Το είδος με τους περισσότερους «χαμένους» κύκλους αγορών και ο λόγος μέρες-από-αγορά / κύκλος."""
    best, ratio = None, None
    for l in s["LINES"]:
        e = l.get("evidence") or {}
        if not e.get("last_purchase_date") or not e.get("avg_interval_days"):
            continue
        r = (CUTOFF - _d(e["last_purchase_date"])).days / e["avg_interval_days"]
        if ratio is None or r > ratio:
            best, ratio = l, r
    return best, ratio


def priority_of(s: dict) -> str:
    r = worst_line(s)[1] or 0
    if r >= LOST_RATIO:
        return "lost"
    if s["urgency"] == "high" and r >= CRITICAL_RATIO:
        return "critical"
    return s["urgency"]


def pick(suggestions: list[dict], salesman: int | None = None, suggestion_id: str | None = None) -> dict:
    """Ο πιο επείγων ανοιχτός πελάτης (κρίσιμος → αξία → πρώτη εξάντληση). Οι «πιθανή απώλεια» θέλουν τηλέφωνο
    στον πελάτη, όχι παραγγελία — δεν τους διαλέγουμε για demo παραγγελίας."""
    if suggestion_id:
        s = next((x for x in suggestions if x["id"] == suggestion_id), None)
        if not s or s["status"] not in OPEN:
            raise NoSuggestion("η πρόταση δεν υπάρχει ή δεν είναι ανοιχτή")
        return s
    pool = [s for s in suggestions if s["status"] in OPEN and (salesman is None or s["SALESMAN"] == salesman)
            and priority_of(s) != "lost"]
    if not pool:
        raise NoSuggestion("δεν υπάρχει ανοιχτή πρόταση για αυτόν τον πωλητή")
    pool.sort(key=lambda s: (PRIORITY_ORDER[priority_of(s)], -(s.get("VALUE") or 0),
                             s["LINES"][0]["PREDICTED_DEPLETION_DATE"]))
    return pool[0]


# ---------------- κείμενα (μόνο από τα δεδομένα της πρότασης) ----------------
def dm(iso: str) -> str:
    d = _d(iso)
    return f"{d.day}/{d.month}"


def day(iso: str) -> str:
    return f"{WEEKDAYS[_d(iso).weekday()]} {dm(iso)}"


def qty(n: int, unit: str) -> str:
    one, many = UNITS.get(unit, ("μονάδα", "μονάδες"))
    return f"{n} {one if n == 1 else many}"


def eur(v: float | None) -> str:
    return f"{round(v or 0):,}".replace(",", ".") + " ευρώ"


def item(name: str) -> str:
    """«Ice tea λεμόνι 500ml κιβ. 12τεμ» → «Ice tea λεμόνι 500ml» (η συσκευασία δεν λέγεται στο τηλέφωνο)."""
    return name.split(" κιβ.")[0].strip()


def vocative(first: str) -> str:
    """Στέλιος → Στέλιο, Γιάννης → Γιάννη, Λουκάς → Λουκά."""
    for a, b in (("ος", "ο"), ("ης", "η"), ("ας", "α")):
        if first.endswith(a):
            return first[: -len(a)] + b
    return first


def short(name: str) -> str:
    """«Μπύρα λευκή 500ml κιβ. 12τεμ» → «μπύρα λευκή» (όπως θα το έλεγε ο πωλητής)."""
    words = []
    for w in name.split():
        if any(ch.isdigit() for ch in w) or w.endswith(".") or len(words) == 2:
            break
        words.append(w)
    return " ".join(words or name.split()[:1]).lower()


def items_phrase(s: dict, limit: int = 3, first: dict | None = None, tail: str = "") -> str:
    lines = s["LINES"]
    if first is not None:                                       # το είδος της συζήτησης πρώτο
        lines = sorted(lines, key=lambda l: l["MTRL"] != first["MTRL"])   # σταθερή ταξινόμηση· τρέχουσα ποσότητα
    out = ", ".join(f"{qty(l['QTY1'], l['UNIT'])} {item(l['ITEM_NAME'])}" for l in lines[:limit])
    rest = len(lines) - limit
    if rest > 0:
        out += f" και {'ένα ακόμα είδος' if rest == 1 else f'άλλα {rest} είδη'}{tail}"
    return out


def risk_line(s: dict) -> str:
    """Γιατί ο πελάτης κινδυνεύει — από το evidence του χειρότερου είδους."""
    l, ratio = worst_line(s)
    if l is None:
        l = min(s["LINES"], key=lambda x: x["PREDICTED_DEPLETION_DATE"])
        return f"{item(l['ITEM_NAME'])}: εκτιμώ ότι τελειώνει γύρω στις {dm(l['PREDICTED_DEPLETION_DATE'])}."
    e = l["evidence"]
    since = (CUTOFF - _d(e["last_purchase_date"])).days
    iv = round(e["avg_interval_days"])
    base = (f"Στο {item(l['ITEM_NAME'])} η τελευταία παραλαβή ήταν {qty(int(e['last_purchase_qty']), l['UNIT'])} "
            f"στις {dm(e['last_purchase_date'])}, ενώ συνήθως παραγγέλνει κάθε {iv} μέρες")
    if ratio is not None and ratio >= CRITICAL_RATIO:
        return f"{base}. Έχουν περάσει ήδη {since} μέρες, οπότε πιθανότατα έχει ήδη ξεμείνει."
    return f"{base}. Εκτιμώ ότι τελειώνει γύρω στις {dm(l['PREDICTED_DEPLETION_DATE'])}."


# ---------------- η κλήση ----------------
class CallSimulator:
    """actions: get(sid), change_qty(sid, mtrl, qty, version), confirm(sid, version) -> token,
    create_draft(sid, token, idem) -> {"erp_draft_id"}, event(dict) — τα ίδια endpoints με τον voice agent."""

    def __init__(self, suggestions: Callable[[], list[dict]], actions: dict[str, Callable], pace: float | None = None):
        self.suggestions, self.a = suggestions, actions
        self.pace = float(os.environ.get("CALL_SIM_PACE", "1")) if pace is None else pace
        self.lock = threading.Lock()
        self.running: str | None = None

    def start(self, salesman: int | None = None, suggestion_id: str | None = None, wait: bool = False) -> dict:
        with self.lock:
            if self.running:
                raise Busy(self.running)
            s = pick(self.suggestions(), salesman, suggestion_id)
            sid = f"SIM-{time.strftime('%H%M%S')}-{secrets.token_hex(2)}"
            self.running = sid
        self.a["event"]({"call_sid": sid, "salesman": s["SALESMAN"], "suggestion_id": s["id"], "status": "dialing"})
        out = {"call_sid": sid, "suggestion_id": s["id"], "customer": s["CUSTOMER_NAME"], "priority": priority_of(s),
               "salesman": s["SALESMAN"], "status": "dialing"}
        t = threading.Thread(target=self._run, args=(sid, s), daemon=True)
        t.start()
        if wait:
            t.join()
        return out

    # ---- εσωτερικά ----
    def _wait(self, sec: float) -> None:
        if self.pace > 0:
            time.sleep(sec * self.pace)

    def _say(self, sid: str, role: str, text: str, **ev) -> None:
        self.a["event"]({"call_sid": sid, "role": role, "text": text, **ev})
        # χρόνος ≈ όσο θα κρατούσε η φράση στο τηλέφωνο, για να προλαβαίνει και η φωνή του browser
        self._wait(max(1.4, len(text) / (14 if role == "agent" else 12)))

    def _run(self, sid: str, s: dict) -> None:
        try:
            self._script(sid, s)
        except Exception as e:  # noqa: BLE001
            log.exception("simulation failed")
            self.a["event"]({"call_sid": sid, "status": "failed", "role": "agent",
                             "text": f"Η κλήση διακόπηκε ({e}). Δεν καταχωρήθηκε τίποτα."})
        finally:
            with self.lock:
                self.running = None

    def _script(self, sid: str, s: dict) -> None:
        ev = self.a["event"]
        first = vocative(s["SALESMAN_NAME"].split()[0]) if s.get("SALESMAN_NAME") else ""
        self._wait(2.2)
        ev({"call_sid": sid, "status": "connected"})
        self._wait(0.8)
        self._say(sid, "agent", f"Καλημέρα{' ' + first if first else ''}, είμαι η VORA, ο ψηφιακός βοηθός παραγγελιών — "
                                f"σας μιλάει πρόγραμμα AI. Έχετε ένα λεπτό για έναν πελάτη σας που κινδυνεύει να ξεμείνει;")
        self._say(sid, "user", "Ναι, πες μου.")

        ev({"call_sid": sid, "status": "discussing"})
        self._say(sid, "agent", f"Ο πιο επείγων πελάτης σήμερα: {s['CUSTOMER_NAME']}, στην περιοχή {s['AREA']}. {risk_line(s)}")
        self._say(sid, "user", "Δεν μου έχει πει τίποτα. Τι προτείνεις να του στείλουμε;")
        conf = max(l.get("CONFIDENCE") or 0 for l in s["LINES"])
        hot = worst_line(s)[0] or min(s["LINES"], key=lambda x: x["PREDICTED_DEPLETION_DATE"])
        self._say(sid, "agent", f"Προτείνω {items_phrase(s, first=hot)}, αξία περίπου {eur(s.get('VALUE'))}, με παράδοση {day(s['SUGGESTED_DELIVERY_DATE'])}. "
                                f"Οι ποσότητες βγαίνουν από το ιστορικό τιμολογίων του, με σιγουριά γύρω στο {round(conf * 100)}%.")

        # ο πωλητής αλλάζει μία ποσότητα — περνά από τον ίδιο έλεγχο ορίων με τη φωνή και το dashboard
        l = hot
        new = min(l["QTY_MAX"], l["QTY1"] + max(1, round(l["QTY1"] * 0.5)))
        if new != l["QTY1"]:
            self._say(sid, "user", f"Το {short(l['ITEM_NAME'])} κάν' το {qty(new, l['UNIT'])}, τα υπόλοιπα όπως τα λες.")
            s = self.a["change_qty"](s["id"], l["MTRL"], new, s["version"])
            self._say(sid, "agent", f"Έγινε: {item(l['ITEM_NAME'])}, {qty(new, l['UNIT'])}. Η αξία γίνεται περίπου {eur(s.get('VALUE'))}.",
                      status="quantity_modified")
        else:
            self._say(sid, "user", "Εντάξει, όπως τα λες.")

        self._say(sid, "agent", f"Επιβεβαιώνετε πρόχειρη παραγγελία για {s['CUSTOMER_NAME']}: {items_phrase(s, 2, hot, ' στις ποσότητες της πρότασης')}, "
                                f"με παράδοση {day(s['SUGGESTED_DELIVERY_DATE'])}; Αν ναι, πείτε «ναι, επιβεβαιώνω».",
                  status="confirming")
        self._say(sid, "user", "Ναι, επιβεβαιώνω.", status="explicit_confirmation")

        self._say(sid, "agent", "Τη στέλνω στο ERP ως πρόχειρη…", status="posting_draft")
        tok = self.a["confirm"](s["id"], s["version"])
        r = self.a["create_draft"](s["id"], tok, f"{sid}:{s['id']}:v{s['version']}")
        did = r["erp_draft_id"]
        self._say(sid, "agent", f"Έγινε. Το πρόχειρο {did} είναι στο ERP και περιμένει έλεγχο πριν εκτελεστεί.",
                  status="draft_created", erp_draft_id=did)
        self._say(sid, "user", "Τέλεια, ευχαριστώ.")
        self._say(sid, "agent", "Καλή συνέχεια! Τους υπόλοιπους πελάτες τους βλέπετε στο dashboard.")
