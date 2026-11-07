"""Ελληνική εξήγηση μιας πρότασης — grounded ΜΟΝΟ στο evidence.

Το LLM δεν βγάζει αριθμούς: του δίνουμε τα πεδία και του απαγορεύουμε να προσθέσει νέα νούμερα.
Αν δεν υπάρχουν credentials ή το API αποτύχει → deterministic template από τα ίδια πεδία.
"""
from __future__ import annotations

import json
import logging
import os

import anthropic

log = logging.getLogger("explain")
MODEL = os.environ.get("EXPLAIN_MODEL", "claude-opus-5-5")
GROUNDED_FIELDS = ["PREDICTED_DEPLETION_DATE", "QTY1", "UNIT", "burn_rate_per_day", "burn_rate_recent_per_day",
                   "last_purchase_date", "last_purchase_qty", "avg_interval_days", "seasonal_multiplier",
                   "promo", "cold_start", "peer_group", "warnings"]

SYSTEM = """Είσαι βοηθός πωλήσεων σε χονδρέμπορο τροφίμων/ποτών. Εξηγείς σε έναν πωλητή γιατί το σύστημα
προτείνει μια παραγγελία για έναν πελάτη του. Τα στοιχεία έρχονται από μοντέλο πρόβλεψης πάνω στο ιστορικό τιμολογίων
(όχι από απογραφή του πελάτη).

Κανόνες:
- Το πολύ 3 σύντομες προτάσεις στα ελληνικά, απλό επαγγελματικό ύφος, χωρίς λίστες ή επικεφαλίδες.
- Μίλα για το πιο επείγον είδος (το πρώτο) και πες πόσα ακόμη είδη έχει η πρόταση. Μην απαριθμήσεις τα υπόλοιπα.
- Χρησιμοποίησε ΜΟΝΟ τα στοιχεία του JSON. Μην προσθέσεις αριθμούς, ημερομηνίες, προσφορές ή αιτίες που δεν υπάρχουν εκεί.
- Αν ένα πεδίο είναι null ή λείπει, μην το αναφέρεις.
- Η εποχικότητα «συσχετίζεται με την εποχή» — μην πεις ότι την προκαλεί.
- Μια προσφορά στο μέλλον ΔΕΝ αλλάζει την ημερομηνία εξάντλησης· αν υπάρχει, ανέφερέ τη μόνο ως ευκαιρία πώλησης.
- Αριθμούς ακριβώς όπως δίνονται, με κόμμα για δεκαδικά (0,14). Ημερομηνίες ως «6 Νοεμβρίου»."""

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic | None:
    global _client
    if _client is None:
        try:
            _client = anthropic.Anthropic()
        except Exception as e:                     # χωρίς credentials
            log.warning("no Anthropic credentials: %s", e)
            return None
    return _client


def _r2(v):
    return None if v is None else round(float(v), 2)


def _line(l: dict) -> dict:
    """Τα πεδία με περιγραφικά ελληνικά ονόματα — ώστε το LLM να μην παρερμηνεύει τι είναι κάθε ρυθμός."""
    e = l["evidence"]
    out = {
        "είδος": l["ITEM_NAME"],
        "εκτιμώμενη_εξάντληση": l["PREDICTED_DEPLETION_DATE"],
        "προτεινόμενη_ποσότητα": l["QTY1"],
        "μονάδα": l["UNIT"],
        "κατανάλωση_ανά_μέρα_τις_επόμενες_εβδομάδες": _r2(e.get("burn_rate_per_day")),
        "κατανάλωση_ανά_μέρα_τις_τελευταίες_90_μέρες": _r2(e.get("burn_rate_recent_per_day")),
        "τελευταία_παραλαβή_ημερομηνία": e.get("last_purchase_date"),
        "τελευταία_παραλαβή_ποσότητα": e.get("last_purchase_qty"),
        "αγοράζει_κάθε_περίπου_μέρες": e.get("avg_interval_days"),
        "παράγοντες": [f["source"] for f in e.get("factors", []) if f.get("name") != "purchase_cycle"],
        "προσφορά_στο_μέλλον": e.get("promo"),
        "νέος_πελάτης": e.get("cold_start") or None,
        "παρόμοιοι_πελάτες": e.get("peer_group"),
        "προειδοποιήσεις": e.get("warnings") or None,
    }
    return {k: v for k, v in out.items() if v not in (None, [], "")}


def bundle(s: dict) -> dict:
    return {"πελάτης": s["CUSTOMER_NAME"], "τύπος": s["CUSTOMER_CATEGORY"], "περιοχή": s["AREA"],
            "προτεινόμενη_παράδοση": s["SUGGESTED_DELIVERY_DATE"],
            "πιο_επείγον_είδος": _line(s["LINES"][0]), "υπόλοιπα_είδη_στην_πρόταση": len(s["LINES"]) - 1}


MONTHS = ["Ιανουαρίου", "Φεβρουαρίου", "Μαρτίου", "Απριλίου", "Μαΐου", "Ιουνίου", "Ιουλίου",
          "Αυγούστου", "Σεπτεμβρίου", "Οκτωβρίου", "Νοεμβρίου", "Δεκεμβρίου"]


def gr_date(iso: str | None) -> str:
    if not iso:
        return "–"
    y, m, d = iso.split("-")
    return f"{int(d)} {MONTHS[int(m) - 1]}"


def gr_num(v: float, digits: int = 1) -> str:
    return f"{v:.{digits}f}".replace(".", ",")


def template(s: dict) -> str:
    l = s["LINES"][0]; e = l["evidence"]
    t = (f"Για τον πελάτη {s['CUSTOMER_NAME']}, το {l['ITEM_NAME']} εκτιμάται ότι τελειώνει στις {gr_date(l['PREDICTED_DEPLETION_DATE'])}: "
         f"η τελευταία παραλαβή ήταν {e['last_purchase_qty']} {l['UNIT']} στις {gr_date(e['last_purchase_date'])} "
         f"και καταναλώνει περίπου {gr_num(e['burn_rate_per_day'])} {l['UNIT']} τη μέρα.")
    if e.get("avg_interval_days"):
        t += f" Συνήθως παραγγέλνει κάθε {e['avg_interval_days']:.0f} μέρες."
    if e.get("promo"):
        t += f" Ισχύει {e['promo']['name']} ({gr_date(e['promo']['from'])} – {gr_date(e['promo']['to'])})."
    if e.get("cold_start"):
        t += f" Νέος πελάτης: η πρόβλεψη στηρίζεται και σε παρόμοιους ({e.get('peer_group')})."
    if len(s["LINES"]) > 1:
        t += f" Η πρόταση περιλαμβάνει ακόμη {len(s['LINES']) - 1} είδη."
    return t


def explain(s: dict) -> dict:
    b = bundle(s)
    client = _get_client()
    if client is not None:
        try:
            r = client.beta.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=SYSTEM,
                output_config={"effort": "low"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                messages=[{"role": "user", "content": json.dumps(b, ensure_ascii=False)}],
            )
            if r.stop_reason != "refusal":
                text = "".join(blk.text for blk in r.content if blk.type == "text").strip()
                if text:
                    return {"text": text, "source": "llm", "model": r.model, "grounded_on": GROUNDED_FIELDS}
            log.warning("explanation refused or empty (stop_reason=%s)", r.stop_reason)
        except anthropic.APIConnectionError as e:
            log.warning("LLM connection error: %s", e)
        except anthropic.RateLimitError as e:
            log.warning("LLM rate limited: %s", e)
        except anthropic.APIStatusError as e:
            log.warning("LLM error %s: %s", e.status_code, e.message)
        except anthropic.AnthropicError as e:
            log.warning("LLM unavailable: %s", e)
        except TypeError as e:                     # το SDK το πετάει όταν δεν βρίσκει credentials
            log.warning("no Anthropic credentials: %s", e)
    return {"text": template(s), "source": "template", "model": None, "grounded_on": GROUNDED_FIELDS}
