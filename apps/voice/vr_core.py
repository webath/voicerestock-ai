"""vr_core.py — Η λογική του VoiceRestock voice agent, ΧΩΡΙΣ pipecat/LiveKit.

Εδώ ζουν οι κανόνες ασφαλείας και ό,τι λέγεται φωναχτά, ώστε να ελέγχονται με unit tests
(`python3 -m unittest discover apps/voice/tests`) χωρίς τηλέφωνο:

- ελληνικές λέξεις για ποσότητες και ημερομηνίες (το φωνητικό μοντέλο εκφωνεί λάθος τα ψηφία),
- περιγραφή προτάσεων/εξήγηση ΜΟΝΟ από το `evidence` του App API (ποτέ αριθμοί από το LLM),
- `CallSession`: τα εργαλεία της κλήσης. Το LLM δίνει μόνο ids/ποσότητα· ο server ελέγχει
  ιδιοκτησία, όρια, version, διπλή επιβεβαίωση και exactly-once draft. Το confirmation token
  του App API μένει εδώ και δεν φτάνει ποτέ στο LLM.

Python 3.9-συμβατό (τα tests τρέχουν και στο Mac με το system python).
"""
from __future__ import annotations

import asyncio
import re
import time
from datetime import date
from typing import Any, Awaitable, Callable, Optional

# ---------------------------------------------------------------------------
# Ελληνικά νούμερα / ημερομηνίες
# ---------------------------------------------------------------------------
_N = ["μηδέν", "ένα", "δύο", "τρία", "τέσσερα", "πέντε", "έξι", "επτά", "οκτώ", "εννιά", "δέκα",
      "έντεκα", "δώδεκα", "δεκατρία", "δεκατέσσερα", "δεκαπέντε", "δεκαέξι", "δεκαεπτά", "δεκαοκτώ", "δεκαεννιά"]
_F = {1: "μία", 3: "τρεις", 4: "τέσσερις", 13: "δεκατρείς", 14: "δεκατέσσερις"}  # θηλυκό όπου διαφέρει
_TENS = {2: "είκοσι", 3: "τριάντα", 4: "σαράντα", 5: "πενήντα", 6: "εξήντα", 7: "εβδομήντα", 8: "ογδόντα", 9: "ενενήντα"}
_HUND = {1: "εκατό", 2: "διακόσια", 3: "τριακόσια", 4: "τετρακόσια", 5: "πεντακόσια", 6: "εξακόσια",
         7: "επτακόσια", 8: "οκτακόσια", 9: "εννιακόσια"}
MONTHS_GEN = ["Ιανουαρίου", "Φεβρουαρίου", "Μαρτίου", "Απριλίου", "Μαΐου", "Ιουνίου", "Ιουλίου",
              "Αυγούστου", "Σεπτεμβρίου", "Οκτωβρίου", "Νοεμβρίου", "Δεκεμβρίου"]
WEEKDAYS_ACC = ["τη Δευτέρα", "την Τρίτη", "την Τετάρτη", "την Πέμπτη", "την Παρασκευή", "το Σάββατο", "την Κυριακή"]
UNITS = {"ΚΙΒ": ("κιβώτιο", "κιβώτια"), "ΤΕΜ": ("τεμάχιο", "τεμάχια")}


def num_words(n: int, feminine: bool = False) -> str:
    """Ακέραιος 0..999.999 σε λέξεις (ουδέτερο, ή θηλυκό για ημέρες/χιλιάδες). Μεγαλύτεροι μένουν ψηφία."""
    if n < 0 or n >= 1_000_000:
        return str(n)
    if n >= 2000:
        th, rest = divmod(n, 1000)
        return f"{num_words(th, feminine=True)} χιλιάδες" + (f" {num_words(rest, feminine)}" if rest else "")
    if n >= 1000:
        rest = n - 1000
        return "χίλια" + (f" {num_words(rest, feminine)}" if rest else "")
    if n >= 100:
        h, rest = divmod(n, 100)
        if not rest:
            return _HUND[h]
        return ("εκατόν" if h == 1 else _HUND[h]) + " " + num_words(rest, feminine)
    if n >= 20:
        t, u = divmod(n, 10)
        return _TENS[t] + (f" {num_words(u, feminine)}" if u else "")
    return _F.get(n, _N[n]) if feminine else _N[n]


def qty_words(qty: int, unit: str) -> str:
    """4, 'ΚΙΒ' → «τέσσερα κιβώτια»· 1 → «ένα κιβώτιο»."""
    one, many = UNITS.get(unit, ("μονάδα", "μονάδες"))
    if unit not in UNITS:  # θηλυκό «μονάδα»
        return f"{num_words(qty, feminine=True)} {one if qty == 1 else many}"
    return f"{num_words(qty)} {one if qty == 1 else many}"


def unit_plural(unit: str) -> str:
    return UNITS.get(unit, ("μονάδα", "μονάδες"))[1]


def _d(iso: str) -> date:
    return date.fromisoformat(str(iso)[:10])


def spoken_day_month(iso: str) -> str:
    """2026-11-03 → «τρεις Νοεμβρίου»· 2026-11-01 → «πρώτη Νοεμβρίου»."""
    d = _d(iso)
    day = "πρώτη" if d.day == 1 else num_words(d.day, feminine=True)
    return f"{day} {MONTHS_GEN[d.month - 1]}"


def spoken_date(iso: str) -> str:
    """2026-11-03 → «την Τρίτη τρεις Νοεμβρίου»."""
    return f"{WEEKDAYS_ACC[_d(iso).weekday()]} {spoken_day_month(iso)}"


def euro_words(v) -> str:
    """1275.6 → «χίλια διακόσια εβδομήντα έξι ευρώ» (στρογγυλό ευρώ· τιμές καταλόγου, όχι τελική τιμή)."""
    return f"{num_words(int(round(float(v))))} ευρώ"


def spoken_digits(s: str) -> str:
    """'0001' → «μηδέν μηδέν μηδέν ένα» (για κωδικούς: ψηφίο-ψηφίο)."""
    return " ".join(_N[int(c)] for c in s if c.isdigit())


_LEGAL = re.compile(r"\s+(Α\.?Ε\.?|Μ\.?Ε\.?Π\.?Ε\.?|Ε\.?Π\.?Ε\.?|Ο\.?Ε\.?|Ε\.?Ε\.?|Ι\.?Κ\.?Ε\.?)\s*$")


def spoken_customer(name: str) -> str:
    """«Mini Market Οικονομικό Μ.Ε.Π.Ε.» → «Mini Market Οικονομικό» (η νομική μορφή δεν λέγεται)."""
    return _LEGAL.sub("", name or "").strip()


def spoken_item(name: str) -> str:
    """«Νερό 0,5L κιβ. 24τεμ» → «Νερό μισό λίτρο». Η συσκευασία δεν λέγεται· η μονάδα λέγεται με την ποσότητα."""
    s = re.sub(r"\s*κιβ\..*$", "", name or "")          # «κιβ. 24τεμ», «κιβ. 10 συσκ.»: συσκευασία, δεν λέγεται
    w = lambda n: num_words(int(n))                     # noqa: E731

    def decimal_litres(m):
        v = float(f"{m.group(1)}.{m.group(2)}")
        if v == 1.5:
            return "ενάμισι λίτρο"
        if v == 0.5:
            return "μισό λίτρο"
        return f"{w(round(v * 1000))} ml" if v < 1 else f"{w(m.group(1))} κόμμα {w(m.group(2))} λίτρα"
    s = re.sub(r"(\d+)[,.](\d+)\s*L\b", decimal_litres, s)
    unit = lambda one, many: (lambda m: f"{w(m.group(1))} {one if m.group(1) == '1' else many}")  # noqa: E731
    s = re.sub(r"(\d+)\s*L\b", unit("λίτρο", "λίτρα"), s)
    s = re.sub(r"(\d+)\s*kg\b", unit("κιλό", "κιλά"), s)
    s = re.sub(r"(\d+)\s*ml\b", lambda m: f"{w(m.group(1))} ml", s)
    s = re.sub(r"(\d+)\s*g\b", unit("γραμμάριο", "γραμμάρια"), s)
    s = re.sub(r"(\d+)\s*cm\b", unit("εκατοστό", "εκατοστά"), s)
    s = re.sub(r"(\d+)\s*m\b", unit("μέτρο", "μέτρα"), s)
    s = re.sub(r"(\d+)\s*τεμ\.?", unit("τεμάχιο", "τεμάχια"), s)
    s = re.sub(r"(\d+)x(\d+)", lambda m: f"{w(m.group(1))} επί {w(m.group(2))}", s)
    s = re.sub(r"\d+", lambda m: w(m.group(0)), s)      # ό,τι έμεινε (π.χ. «12 ρολά»)
    return " ".join(s.split())


def spoken_promo(promo: dict) -> str:
    """{'name': 'Προσφορά Μπύρες -10%', 'disc_prc': 10} → «προσφορά για Μπύρες με έκπτωση δέκα τοις εκατό»."""
    what = re.sub(r"\s*-?\s*\d+(?:[.,]\d+)?\s*%", "", promo.get("name") or "")
    what = re.sub(r"^\s*Προσφορά\s*", "", what).strip()
    what = spoken_item(what)
    disc = promo.get("disc_prc")
    pct = f" με έκπτωση {num_words(round(disc))} τοις εκατό" if isinstance(disc, (int, float)) else ""
    return f"προσφορά{' για ' + what if what else ''}{pct}"


def confidence_words(c: Optional[float]) -> str:
    if c is None:
        return "δεν υπάρχει επαρκής ένδειξη για τη βεβαιότητα"
    return "υψηλή βεβαιότητα" if c >= 0.75 else "μέτρια βεβαιότητα" if c >= 0.5 else "χαμηλή βεβαιότητα"


# ---------------------------------------------------------------------------
# Κείμενα από τα δεδομένα του App API
# ---------------------------------------------------------------------------
OPEN_STATUSES = ("proposed", "modified", "confirmed", "failed")


def line_brief(line: dict) -> str:
    dep = line.get("PREDICTED_DEPLETION_DATE")
    ends = f"τελειώνει γύρω στις {spoken_day_month(dep)}" if dep else "δεν προβλέπεται να τελειώσει σύντομα"
    return f"{spoken_item(line['ITEM_NAME'])}: {ends}· πρόταση {qty_words(line['QTY1'], line['UNIT'])}"


def value_phrase(s: dict, list_prices: bool = True) -> str:
    """«, αξία περίπου … ευρώ σε τιμές καταλόγου» — μόνο αν τη δίνει το App API (πεδίο VALUE).
    Στην περίληψη χωρίς «σε τιμές καταλόγου»: ειπώθηκε ήδη στην πρώτη γραμμή και κάθε λέξη εκεί κοστίζει."""
    v = s.get("VALUE")
    if not (isinstance(v, (int, float)) and v > 0):
        return ""
    return f", αξία περίπου {euro_words(v)}" + (" σε τιμές καταλόγου" if list_prices else "")


def suggestion_brief(s: dict) -> str:
    lines = "· ".join(line_brief(l) for l in s["LINES"])
    return (f"{spoken_customer(s['CUSTOMER_NAME'])} ({s['AREA']}): {lines}. "
            f"Παράδοση {spoken_date(s['SUGGESTED_DELIVERY_DATE'])}{value_phrase(s)}.")


def _first_out(s: dict) -> dict:
    """Το είδος που τελειώνει πρώτο (αυτό λέγεται στην πρώτη ατάκα)."""
    return min(s["LINES"], key=lambda l: l.get("PREDICTED_DEPLETION_DATE") or "9999")


def opening_line(s: dict) -> str:
    """ΜΙΑ σύντομη ατάκα ανά πελάτη (~8″): το πρώτο είδος που τελειώνει, πόσα ακόμα, αξία, παράδοση.
    Στις πρώτες κλήσεις η πλήρης περιγραφή όλων των ειδών κρατούσε ~20″ και ο πωλητής διέκοπτε."""
    l = _first_out(s)
    rest = len(s["LINES"]) - 1
    dep = l.get("PREDICTED_DEPLETION_DATE")
    when = f" γύρω στις {spoken_day_month(dep)}" if dep else ""
    more = "" if rest <= 0 else (", και ένα ακόμα είδος" if rest == 1 else f", και άλλα {num_words(rest)} είδη")
    return (f"{spoken_customer(s['CUSTOMER_NAME'])}: τελειώνει πρώτα {spoken_item(l['ITEM_NAME'])}{when}{more}"
            f"{value_phrase(s)}. Παράδοση {spoken_date(s['SUGGESTED_DELIVERY_DATE'])}.")


def items_list(s: dict) -> str:
    """Όλα τα είδη με ποσότητα και εξάντληση — μόνο όταν ο πωλητής ρωτήσει «τι άλλο;»."""
    return "· ".join(line_brief(l) for l in s["LINES"]) + "."


READ_BACK_FULL = 3   # μέχρι τόσα είδη διαβάζονται όλα· πάνω από αυτό: τα αλλαγμένα + τα πρώτα, ως 2


def read_back(s: dict) -> str:
    """Η περίληψη που επιβεβαιώνει ο πωλητής. Λέει ΠΑΝΤΑ: πελάτη, κάθε είδος που άλλαξε ο πωλητής, παράδοση.
    Σε μεγάλη πρόταση τα υπόλοιπα είδη λέγονται ως «στις ποσότητες της πρότασης» (ίδια με το dashboard),
    αλλιώς η κλήση κρατά μισό λεπτό και ο πωλητής διακόπτει (πρώτη κλήση με πραγματικά δεδομένα, 7/11)."""
    lines = s["LINES"]
    say = lambda l: f"{spoken_item(l['ITEM_NAME'])} {qty_words(l['QTY1'], l['UNIT'])}"  # noqa: E731
    if len(lines) <= READ_BACK_FULL:
        items = ", ".join(say(l) for l in lines)
    else:
        changed = [l for l in lines if l["QTY1"] != l.get("QTY_RECOMMENDED", l["QTY1"])]
        shown = changed + [l for l in lines if l not in changed][: max(0, 2 - len(changed))]
        rest = len(lines) - len(shown)
        items = ", ".join(say(l) for l in shown)
        if rest:
            items += f", και {'ένα ακόμα είδος' if rest == 1 else num_words(rest) + ' ακόμα είδη'} στις ποσότητες της πρότασης"
    return (f"Επιβεβαιώνετε πρόχειρη παραγγελία για τον πελάτη {spoken_customer(s['CUSTOMER_NAME'])}: {items}, "
            f"με παράδοση {spoken_date(s['SUGGESTED_DELIVERY_DATE'])}{value_phrase(s, list_prices=False)};")


def explain_line(line: dict) -> str:
    """Εξήγηση ΜΟΝΟ από το evidence. Ό,τι λείπει → «δεν υπάρχει επαρκής ένδειξη»."""
    e = line.get("evidence") or {}
    unit = line.get("UNIT", "")
    out = []
    rate = e.get("burn_rate_per_day")
    if isinstance(rate, (int, float)) and rate > 0:
        week = round(rate * 7)
        out.append(f"Καταναλώνει περίπου {qty_words(week, unit)} την εβδομάδα" if week >= 1
                   else f"Καταναλώνει λιγότερο από ένα {UNITS.get(unit, ('μονάδα',))[0]} την εβδομάδα")
    else:
        out.append("Για τον ρυθμό κατανάλωσης δεν υπάρχει επαρκής ένδειξη")
    if e.get("last_purchase_date") and isinstance(e.get("last_purchase_qty"), (int, float)):
        out.append(f"η τελευταία παραλαβή ήταν {qty_words(int(e['last_purchase_qty']), unit)} "
                   f"στις {spoken_day_month(e['last_purchase_date'])}")
    if isinstance(e.get("avg_interval_days"), (int, float)) and e["avg_interval_days"] >= 1:
        out.append(f"συνήθως παραγγέλνει κάθε {num_words(round(e['avg_interval_days']), feminine=True)} ημέρες")
    sm = e.get("seasonal_multiplier")
    if isinstance(sm, (int, float)):
        if sm < 0.95:
            out.append("αυτή την εποχή η κατανάλωση συνήθως πέφτει")
        elif sm > 1.05:
            out.append("αυτή την εποχή η κατανάλωση συνήθως ανεβαίνει")
    promo = e.get("promo")
    if promo:
        out.append(f"ισχύει {spoken_promo(promo)} από {spoken_day_month(promo['from'])} "
                   f"έως {spoken_day_month(promo['to'])}")
    if e.get("cold_start"):
        peers = f" ({e['peer_group']})" if e.get("peer_group") else ""
        out.append(f"είναι νέος πελάτης, οπότε η πρόβλεψη στηρίζεται σε παρόμοιους πελάτες{peers}")
    out.append(f"το σύστημα δίνει {confidence_words(line.get('CONFIDENCE'))}")
    text = ", ".join(out) + "."
    for w in e.get("warnings") or []:
        text += f" Προσοχή: {w}."
    return text[0].upper() + text[1:]


# ---------------------------------------------------------------------------
# Προτεραιότητα — ΙΔΙΑ με το dashboard (apps/web/lib/priority.ts), ώστε η κλήση να ξεκινά από
# τους ίδιους πελάτες με τη λίστα «Με ποιους να ξεκινήσεις». Το `urgency` του contract δεν αλλάζει.
# ---------------------------------------------------------------------------
CUTOFF = "2026-10-31"
CRITICAL_RATIO = 1.5   # έχει χάσει μισό κύκλο αγορών ή παραπάνω → μάλλον έχει ήδη ξεμείνει
LOST_RATIO = 3.0       # τρεις κύκλοι χωρίς αγορά → μάλλον τον χάσαμε· θέλει τηλέφωνο, όχι παραγγελία
PRIORITY_ORDER = {"critical": 0, "high": 1, "lost": 2, "medium": 3, "low": 4}


def priority_of(s: dict) -> "tuple[str, Optional[float]]":
    """(προτεραιότητα, κύκλοι χωρίς αγορά στο χειρότερο είδος)."""
    worst = None
    for l in s.get("LINES", []):
        e = l.get("evidence") or {}
        if not e.get("last_purchase_date") or not e.get("avg_interval_days"):
            continue
        ratio = (_d(CUTOFF) - _d(e["last_purchase_date"])).days / e["avg_interval_days"]
        worst = ratio if worst is None or ratio > worst else worst
    r = worst or 0
    if r >= LOST_RATIO:
        return "lost", worst
    if s.get("urgency") == "high" and r >= CRITICAL_RATIO:
        return "critical", worst
    return s.get("urgency", "low"), worst


def priority_sort_key(s: dict):
    """Επίπεδο → αξία (€, αν τη δίνει το API) → πρώτη εξάντληση. Όπως το byPriority του dashboard."""
    first = (s.get("LINES") or [{}])[0].get("PREDICTED_DEPLETION_DATE") or "9999"
    return (PRIORITY_ORDER.get(priority_of(s)[0], 5), -(s.get("VALUE") or 0), first)


PRIORITY_NOTE = {   # ετικέτες για τη βοηθό· λέγονται σε λίγες λέξεις, όχι αυτούσιες
    "critical": "[ΚΡΙΣΙΜΟ — μάλλον έχει ήδη ξεμείνει] ",
    "lost": "[ΠΙΘΑΝΗ ΑΠΩΛΕΙΑ — δεν αγοράζει εδώ και καιρό· πρότεινε τηλέφωνο στον πελάτη, όχι παραγγελία] ",
}


# ---------------------------------------------------------------------------
# Κλήση: τα εργαλεία με τους κανόνες ασφαλείας
# ---------------------------------------------------------------------------
Request = Callable[..., Awaitable["tuple[int, Any]"]]   # (method, path, body=None) -> (status, json)
_now = time.monotonic


class CallSession:
    """Μία τηλεφωνική κλήση με έναν πωλητή. Ό,τι επιστρέφουν οι μέθοδοι πάει στο LLM (backend)."""

    LARGE_FACTOR = 2   # ποσότητα > 2× της πρότασης → ξανά-επιβεβαίωση («15» vs «50»)

    USER_GRACE_S = 2.5              # το transcript του «ναι» μπορεί να φτάσει λίγο μετά το αίτημα του LLM

    def __init__(self, request: Request, salesman: int, call_id: str,
                 on_event: Optional[Callable[..., Awaitable[None]]] = None, speech_guard: bool = False):
        self.req = request
        self.salesman = salesman
        self.call_id = call_id
        self.on_event = on_event
        self.sugs: dict = {}                 # id -> Suggestion (μόνο του πωλητή)
        self.pending: dict = {}              # id -> version που διαβάστηκε στον πωλητή
        self.large_ok: set = set()           # (id, mtrl, qty) που επιβεβαιώθηκαν ως «μεγάλες»
        self.drafts: dict = {}               # id -> erp_draft_id
        self.status = "queued"
        # Φύλακας ομιλίας (πραγματικές κλήσεις): draft ΜΟΝΟ αν η περίληψη ειπώθηκε ολόκληρη ΚΑΙ ο πωλητής
        # μίλησε ΜΕΤΑ. Στην κλήση της 7/11 ένα «ναι» πάνω στην περίληψη έφτιαξε draft πριν ακουστεί.
        self.speech_guard = speech_guard
        self.prepared_at: dict = {}          # id -> χρόνος του prepare_order
        self.readback_at: Optional[float] = None   # πότε τελείωσε η τελευταία ολοκληρωμένη περίληψη
        self.user_at: Optional[float] = None       # πότε μίλησε τελευταία ο πωλητής

    # ---- τι ειπώθηκε (από τους observers της φωνής) ----
    def note_agent(self, text: str, at: Optional[float] = None):
        """Μια ΟΛΟΚΛΗΡΩΜΕΝΗ φράση της βοηθού (BotStoppedSpeaking). Περίληψη = στην ΙΔΙΑ φράση και η ερώτηση
        «Επιβεβαιώνετε…» και η παράδοση (το τέλος της). Κομμένη περίληψη δεν έχει την παράδοση → δεν μετράει."""
        t = (text or "").lower()
        if "επιβεβαιών" in t and "παράδοση" in t:
            self.readback_at = at if at is not None else _now()

    def note_user(self, text: str, at: Optional[float] = None):
        if (text or "").strip():
            self.user_at = at if at is not None else _now()

    async def _heard_and_answered(self, sid: str) -> Optional[str]:
        """None αν επιτρέπεται το write, αλλιώς ο λόγος (οδηγία για τη βοηθό)."""
        if not self.speech_guard:
            return None
        prep = self.prepared_at.get(sid, 0)
        if self.readback_at is None or self.readback_at < prep:
            return ("Η περίληψη ΔΕΝ ακούστηκε ολόκληρη. Διάβασε ξανά ΟΛΟΚΛΗΡΗ την περίληψη του prepare_order, "
                    "μέχρι και την παράδοση, και περίμενε απάντηση. Δεν δημιουργήθηκε τίποτα.")
        deadline = _now() + self.USER_GRACE_S
        while self.user_at is None or self.user_at <= self.readback_at:
            if _now() >= deadline:
                return ("Ο πωλητής δεν απάντησε ΜΕΤΑ την περίληψη. Ρώτα τον ξανά αν επιβεβαιώνει. "
                        "Δεν δημιουργήθηκε τίποτα.")
            await asyncio.sleep(0.1)
        return None

    # ---- βοηθητικά ----
    async def event(self, **kw):
        if self.on_event:
            try:
                await self.on_event(call_sid=self.call_id, salesman=self.salesman, **kw)
            except Exception:
                pass   # το dashboard δεν πρέπει ποτέ να ρίξει την κλήση

    async def set_status(self, status: str, **kw):
        self.status = status
        await self.event(type="status", status=status, **kw)

    async def load(self) -> list:
        code, data = await self.req("GET", f"/api/suggestions?salesman={self.salesman}")
        if code != 200 or not isinstance(data, list):
            raise RuntimeError(f"App API /api/suggestions: HTTP {code}")
        self.sugs = {s["id"]: s for s in data if s.get("SALESMAN") == self.salesman}
        return [s for s in self.sugs.values() if s["status"] in OPEN_STATUSES]

    async def _fresh(self, sid: str) -> Optional[dict]:
        """Η πρόταση όπως είναι ΤΩΡΑ στο App API — μόνο αν ανήκει στον πωλητή της κλήσης."""
        if sid not in self.sugs:
            await self.load()
            if sid not in self.sugs:
                return None
        code, s = await self.req("GET", f"/api/suggestions/{sid}")
        if code != 200 or s.get("SALESMAN") != self.salesman:
            return None
        self.sugs[sid] = s
        return s

    @staticmethod
    def _err(msg: str, **kw) -> dict:
        return {"status": "error", "message": msg, **kw}

    def catalog(self) -> str:
        """Λίστα για το backend LLM: ids + ό,τι χρειάζεται για να διαλέξει σωστό id/MTRL."""
        rows = []
        for s in self.sugs.values():
            if s["status"] not in OPEN_STATUSES and s["status"] != "draft_created":
                continue
            lines = "; ".join(f"MTRL {l['MTRL']} = {spoken_item(l['ITEM_NAME'])}, ποσότητα {l['QTY1']} {l['UNIT']}"
                              for l in s["LINES"])
            rows.append(f"- {s['id']} | {spoken_customer(s['CUSTOMER_NAME'])} | κατάσταση {s['status']} | {lines}")
        return "\n".join(rows) or "(καμία πρόταση)"

    # ---- εργαλεία ----
    async def overview(self) -> dict:
        open_ = await self.load()
        if not open_:
            return {"status": "ok", "count": 0, "say": "Δεν υπάρχουν ανοιχτές προτάσεις αναπαραγγελίας για τους πελάτες σας."}
        return {"status": "ok", "count": len(open_),
                "suggestions": [{"id": s["id"], "urgency": s["urgency"], "say": suggestion_brief(s)} for s in open_]}

    async def list_items(self, suggestion_id: str) -> dict:
        s = await self._fresh(suggestion_id)
        if not s:
            return self._err("Δεν βρέθηκε αυτή η πρόταση στους πελάτες σας.")
        return {"status": "ok", "say": items_list(s),
                "message": "Πες τα σύντομα· αν είναι πάνω από τέσσερα, πες τα τέσσερα πρώτα και ρώτα αν θέλει τα υπόλοιπα."}

    async def explain(self, suggestion_id: str) -> dict:
        s = await self._fresh(suggestion_id)
        if not s:
            return self._err("Δεν βρέθηκε αυτή η πρόταση στους πελάτες σας.")
        return {"status": "ok", "say": " ".join(f"{spoken_item(l['ITEM_NAME'])}: {explain_line(l)}" for l in s["LINES"])}

    async def change_quantity(self, suggestion_id: str, mtrl: int, qty: int, large_confirmed: bool = False) -> dict:
        s = await self._fresh(suggestion_id)
        if not s:
            return self._err("Δεν βρέθηκε αυτή η πρόταση στους πελάτες σας.")
        line = next((l for l in s["LINES"] if l["MTRL"] == int(mtrl)), None)
        if not line:
            return self._err("Αυτό το είδος δεν είναι στην πρόταση. Δεν προσθέτω είδη που δεν πρότεινε το σύστημα.")
        if isinstance(qty, float) and qty.is_integer():   # το JSON του LLM μπορεί να φέρει 15.0
            qty = int(qty)
        if not isinstance(qty, int) or isinstance(qty, bool):
            return self._err("Η ποσότητα πρέπει να είναι ακέραιος αριθμός.")
        lo, hi = line["QTY_MIN"], line["QTY_MAX"]
        if not lo <= qty <= hi:
            return self._err(f"Η ποσότητα πρέπει να είναι από {qty_words(lo, line['UNIT'])} "
                             f"έως {qty_words(hi, line['UNIT'])}. Ρώτα ξανά τον πωλητή.")
        if qty > self.LARGE_FACTOR * line["QTY_RECOMMENDED"] and not large_confirmed:
            return {"status": "needs_repeat",
                    "say": f"Ακούσατε {qty_words(qty, line['UNIT'])}; Είναι πολύ πάνω από την πρόταση των "
                           f"{qty_words(line['QTY_RECOMMENDED'], line['UNIT'])}.",
                    "message": "Ρώτα τον πωλητή αυτή ακριβώς την ερώτηση. ΜΟΝΟ αν πει καθαρά ναι, ξανακάλεσε "
                               "με large_confirmed=true."}
        if qty == line["QTY1"]:
            return {"status": "ok", "say": f"Η ποσότητα είναι ήδη {qty_words(qty, line['UNIT'])}."}
        code, out = await self.req("POST", f"/api/suggestions/{suggestion_id}/lines/{int(mtrl)}/quantity",
                                   {"qty": qty, "version": s["version"]})
        if code == 409:
            return self._err("Η πρόταση άλλαξε στο μεταξύ ή είναι κλειδωμένη. Διάβασέ τη ξανά.")
        if code != 200:
            return self._err((out or {}).get("message") or f"Αποτυχία αλλαγής (HTTP {code}).")
        self.sugs[suggestion_id] = out
        self.pending.pop(suggestion_id, None)    # ό,τι είχε διαβαστεί πριν δεν ισχύει πια
        await self.event(type="status", status="discussing", suggestion_id=suggestion_id)
        return {"status": "ok", "say": f"{spoken_item(line['ITEM_NAME'])}: η ποσότητα έγινε {qty_words(qty, line['UNIT'])}"
                                       f"{value_phrase(out).replace(', αξία', '· νέα αξία της παραγγελίας')}."}

    async def prepare_order(self, suggestion_id: str) -> dict:
        """Βήμα 1/2: ο πωλητής ζήτησε παραγγελία → διαβάζεται η ακριβής περίληψη. ΚΑΝΕΝΑ write ακόμα."""
        s = await self._fresh(suggestion_id)
        if not s:
            return self._err("Δεν βρέθηκε αυτή η πρόταση στους πελάτες σας.")
        if s["status"] == "draft_created":
            return {"status": "already_created", "say": f"Γι' αυτόν τον πελάτη έχει ήδη δημιουργηθεί πρόχειρη παραγγελία."}
        if s["status"] not in OPEN_STATUSES:
            return self._err(f"Η πρόταση δεν μπορεί να γίνει παραγγελία (κατάσταση {s['status']}).")
        self.pending[suggestion_id] = s["version"]
        self.prepared_at[suggestion_id] = _now()   # μόνο περίληψη που θα ειπωθεί ΜΕΤΑ από εδώ μετράει
        await self.set_status("confirming", suggestion_id=suggestion_id)
        return {"status": "awaiting_confirmation", "say": read_back(s),
                "message": "Διάβασε το «say» ΟΛΟΚΛΗΡΟ και αυτούσιο, τελείωσε με την ερώτηση και ΣΤΑΜΑΤΑ. "
                           "ΤΙΠΟΤΑ δεν έχει δημιουργηθεί: μην πεις «προχωράμε» ή «θα δημιουργηθεί». "
                           "Μόνο αν ο πωλητής απαντήσει ΜΕΤΑ την ερώτηση καθαρά «ναι» → place_draft_order."}

    async def place_draft_order(self, suggestion_id: str) -> dict:
        """Βήμα 2/2: μετά από ρητό «ναι» στην περίληψη → confirm + create-draft, exactly-once."""
        if suggestion_id in self.drafts:
            return {"status": "draft_created", "erp_draft_id": self.drafts[suggestion_id],
                    "say": "Η πρόχειρη παραγγελία έχει ήδη δημιουργηθεί."}
        version = self.pending.get(suggestion_id)
        if version is None:
            return self._err("Δεν έχει διαβαστεί περίληψη για επιβεβαίωση. Κάλεσε πρώτα prepare_order.")
        s = await self._fresh(suggestion_id)
        if not s:
            return self._err("Δεν βρέθηκε αυτή η πρόταση στους πελάτες σας.")
        if s["version"] != version:
            self.pending.pop(suggestion_id, None)
            return self._err("Η πρόταση άλλαξε μετά την περίληψη. Κάλεσε ξανά prepare_order και διάβασέ τη.")
        not_yet = await self._heard_and_answered(suggestion_id)
        if not_yet:
            await self.event(type="status", status="confirming", suggestion_id=suggestion_id,
                             text="Μπλοκαρίστηκε draft: η περίληψη δεν ακούστηκε ολόκληρη πριν το «ναι»")
            return self._err(not_yet, say=read_back(s))
        code, conf = await self.req("POST", f"/api/suggestions/{suggestion_id}/confirm", {"version": version})
        if code != 200 or not conf.get("confirmation_token"):
            return self._err("Η επιβεβαίωση απέτυχε στο σύστημα. Δεν δημιουργήθηκε πρόχειρη παραγγελία.")
        await self.set_status("posting_draft", suggestion_id=suggestion_id)
        key = f"{self.call_id}:{suggestion_id}:v{version}"
        code, out = await self.req("POST", f"/api/suggestions/{suggestion_id}/create-draft",
                                   {"confirmation_token": conf["confirmation_token"], "idempotency_key": key})
        self.pending.pop(suggestion_id, None)
        if code == 200 and out.get("erp_draft_id"):
            did = out["erp_draft_id"]
            self.drafts[suggestion_id] = did
            await self.set_status("draft_created", suggestion_id=suggestion_id, erp_draft_id=did)
            tail = spoken_digits(did.split("-")[-1])
            return {"status": "draft_created", "erp_draft_id": did,
                    "say": f"Το ERP δημιούργησε την πρόχειρη παραγγελία. Ο κωδικός τελειώνει σε {tail} και φαίνεται στο dashboard."}
        await self.set_status("discussing", suggestion_id=suggestion_id)
        return self._err("Το ERP δεν επιβεβαίωσε τη δημιουργία πρόχειρης παραγγελίας. ΔΕΝ δημιουργήθηκε παραγγελία· "
                         "ο πωλητής μπορεί να το δει στο dashboard.", http=code)
