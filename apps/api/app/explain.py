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
προτείνει μια παραγγελία για έναν πελάτη του.

Κανόνες:
- Γράψε 2-3 σύντομες προτάσεις στα ελληνικά, σε απλό, επαγγελματικό ύφος.
- Χρησιμοποίησε ΜΟΝΟ τα στοιχεία του JSON. Μην προσθέσεις αριθμούς, ημερομηνίες, προσφορές ή αιτίες που δεν υπάρχουν εκεί.
- Αν ένα πεδίο είναι null, μην το αναφέρεις· αν λείπει ένδειξη για κάτι, πες «δεν υπάρχει επαρκής ένδειξη».
- Για την εποχικότητα πες «συσχετίζεται με την εποχή», όχι ότι την προκαλεί.
- Στρογγύλεψε ρυθμούς σε 1 δεκαδικό. Ημερομηνίες ως «6 Νοεμβρίου».
- Ξεκίνα από το πιο επείγον είδος. Αν είναι πολλά είδη, ανέφερε το πιο επείγον και πόσα ακόμη υπάρχουν."""

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


def bundle(s: dict) -> dict:
    lines = []
    for l in s["LINES"][:6]:
        e = l["evidence"]
        lines.append({"ITEM_NAME": l["ITEM_NAME"], **{k: (l.get(k) if k in l else e.get(k)) for k in GROUNDED_FIELDS}})
    return {"CUSTOMER_NAME": s["CUSTOMER_NAME"], "CUSTOMER_CATEGORY": s["CUSTOMER_CATEGORY"], "AREA": s["AREA"],
            "SUGGESTED_DELIVERY_DATE": s["SUGGESTED_DELIVERY_DATE"], "lines_total": len(s["LINES"]), "lines": lines}


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
