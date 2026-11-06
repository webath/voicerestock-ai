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

import re
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
    """Ακέραιος 0..1999 σε λέξεις (ουδέτερο, ή θηλυκό για ημέρες του μήνα). Μεγαλύτεροι μένουν ψηφία."""
    if n < 0 or n >= 2000:
        return str(n)
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
    s = re.sub(r"(\d+),(\d+)\s*L\b", decimal_litres, s)
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


def suggestion_brief(s: dict) -> str:
    lines = "· ".join(line_brief(l) for l in s["LINES"])
    return (f"{spoken_customer(s['CUSTOMER_NAME'])} ({s['AREA']}): {lines}. "
            f"Παράδοση {spoken_date(s['SUGGESTED_DELIVERY_DATE'])}.")


def read_back(s: dict) -> str:
    """Η ΑΚΡΙΒΗΣ περίληψη που ακούει ο πωλητής πριν από την επιβεβαίωση."""
    items = ", ".join(f"{spoken_item(l['ITEM_NAME'])} {qty_words(l['QTY1'], l['UNIT'])}" for l in s["LINES"])
    return (f"Επιβεβαιώνετε draft παραγγελίας για τον πελάτη {spoken_customer(s['CUSTOMER_NAME'])}: {items}, "
            f"με παράδοση {spoken_date(s['SUGGESTED_DELIVERY_DATE'])};")


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
# Κλήση: τα εργαλεία με τους κανόνες ασφαλείας
# ---------------------------------------------------------------------------
Request = Callable[..., Awaitable["tuple[int, Any]"]]   # (method, path, body=None) -> (status, json)


class CallSession:
    """Μία τηλεφωνική κλήση με έναν πωλητή. Ό,τι επιστρέφουν οι μέθοδοι πάει στο LLM (backend)."""

    LARGE_FACTOR = 2   # ποσότητα > 2× της πρότασης → ξανά-επιβεβαίωση («15» vs «50»)

    def __init__(self, request: Request, salesman: int, call_id: str,
                 on_event: Optional[Callable[..., Awaitable[None]]] = None):
        self.req = request
        self.salesman = salesman
        self.call_id = call_id
        self.on_event = on_event
        self.sugs: dict = {}                 # id -> Suggestion (μόνο του πωλητή)
        self.pending: dict = {}              # id -> version που διαβάστηκε στον πωλητή
        self.large_ok: set = set()           # (id, mtrl, qty) που επιβεβαιώθηκαν ως «μεγάλες»
        self.drafts: dict = {}               # id -> erp_draft_id
        self.status = "queued"

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
        return {"status": "ok", "say": f"{spoken_item(line['ITEM_NAME'])}: η ποσότητα έγινε {qty_words(qty, line['UNIT'])}."}

    async def prepare_order(self, suggestion_id: str) -> dict:
        """Βήμα 1/2: ο πωλητής ζήτησε παραγγελία → διαβάζεται η ακριβής περίληψη. ΚΑΝΕΝΑ write ακόμα."""
        s = await self._fresh(suggestion_id)
        if not s:
            return self._err("Δεν βρέθηκε αυτή η πρόταση στους πελάτες σας.")
        if s["status"] == "draft_created":
            return {"status": "already_created", "say": f"Γι' αυτόν τον πελάτη έχει ήδη δημιουργηθεί draft."}
        if s["status"] not in OPEN_STATUSES:
            return self._err(f"Η πρόταση δεν μπορεί να γίνει παραγγελία (κατάσταση {s['status']}).")
        self.pending[suggestion_id] = s["version"]
        await self.set_status("confirming", suggestion_id=suggestion_id)
        return {"status": "awaiting_confirmation", "say": read_back(s),
                "message": "Διάβασε αυτό το κείμενο αυτούσιο και ΠΕΡΙΜΕΝΕ σαφές «ναι, επιβεβαιώνω». "
                           "Μόνο τότε κάλεσε place_draft_order. Σε οτιδήποτε άλλο, ΜΗΝ το καλέσεις."}

    async def place_draft_order(self, suggestion_id: str) -> dict:
        """Βήμα 2/2: μετά από ρητό «ναι» στην περίληψη → confirm + create-draft, exactly-once."""
        if suggestion_id in self.drafts:
            return {"status": "draft_created", "erp_draft_id": self.drafts[suggestion_id],
                    "say": "Το draft έχει ήδη δημιουργηθεί."}
        version = self.pending.get(suggestion_id)
        if version is None:
            return self._err("Δεν έχει διαβαστεί περίληψη για επιβεβαίωση. Κάλεσε πρώτα prepare_order.")
        s = await self._fresh(suggestion_id)
        if not s:
            return self._err("Δεν βρέθηκε αυτή η πρόταση στους πελάτες σας.")
        if s["version"] != version:
            self.pending.pop(suggestion_id, None)
            return self._err("Η πρόταση άλλαξε μετά την περίληψη. Κάλεσε ξανά prepare_order και διάβασέ τη.")
        code, conf = await self.req("POST", f"/api/suggestions/{suggestion_id}/confirm", {"version": version})
        if code != 200 or not conf.get("confirmation_token"):
            return self._err("Η επιβεβαίωση απέτυχε στο σύστημα. Δεν δημιουργήθηκε draft.")
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
                    "say": f"Το ERP δημιούργησε το draft. Ο κωδικός τελειώνει σε {tail} και φαίνεται στο dashboard."}
        await self.set_status("discussing", suggestion_id=suggestion_id)
        return self._err("Το ERP δεν επιβεβαίωσε τη δημιουργία draft. ΔΕΝ δημιουργήθηκε παραγγελία· "
                         "ο πωλητής μπορεί να το δει στο dashboard.", http=code)
