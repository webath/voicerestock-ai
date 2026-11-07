"""AI βοηθός του πωλητή: ερωτήσεις στα ελληνικά, απαντήσεις μόνο από τα δεδομένα του συστήματος.

- Claude με εργαλεία ΜΟΝΟ ανάγνωσης (καμία αλλαγή σε παραγγελίες/ERP).
- Streaming: το dashboard βλέπει live ποιο εργαλείο τρέχει και το κείμενο καθώς γράφεται (Server-Sent Events).
- Επίσης: πρωινό briefing ανά πωλητή και μήνυμα προς τον πελάτη (SMS / email) από μια πρόταση.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Callable, Iterator

import anthropic

from .explain import _get_client, gr_date, _line

log = logging.getLogger("assistant")
MODEL = os.environ.get("ASSISTANT_MODEL", "claude-opus-5-5")
MAX_TURNS = 6
FALLBACK = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}

SYSTEM = """Είσαι ο AI βοηθός πωλήσεων της DEMO ΔΙΑΝΟΜΕΣ Α.Ε. (χονδρεμπόριο ποτών, τροφίμων, αναλωσίμων για HoReCa και mini markets).
Σήμερα στο σενάριο είναι Κυριακή 1 Νοεμβρίου 2026. Μιλάς με Account Manager (πωλητή).

Τα δεδομένα: προβλέψεις εξάντλησης αποθέματος ανά πελάτη × είδος (από το ιστορικό τιμολογίων, όχι από απογραφή),
και προτεινόμενες παραγγελίες (drafts) με ποσότητα, αξία και ημερομηνία παράδοσης.

Κανόνες:
- Απαντάς ΠΑΝΤΑ στα ελληνικά, σύντομα και πρακτικά (συνήθως ως 120 λέξεις).
- Για κάθε αριθμό, ημερομηνία ή πελάτη χρησιμοποίησε ΠΡΩΤΑ τα εργαλεία. Ποτέ μην επινοείς στοιχεία.
  Αν κάτι δεν υπάρχει στα δεδομένα, πες το.
- Όταν αναφέρεις πελάτη, βάλε link: [Όνομα πελάτη](/customers/TRDR). Για παραγγελία: [άνοιγμα](/orders?open=SUG-ID).
- Μπορείς να χρησιμοποιείς σύντομες λίστες με «- » και **έντονα** για τα σημαντικά. Όχι πίνακες, όχι επικεφαλίδες.
- Δεν μπορείς να αλλάξεις ή να εγκρίνεις παραγγελίες. Αν το ζητήσουν, παράπεμψε στη σελίδα Παραγγελίες ή στην κλήση.
- Οι μελλοντικές προσφορές δεν αλλάζουν την ημερομηνία εξάντλησης· είναι ευκαιρία πώλησης.
- Ποσά σε € με τελεία για χιλιάδες (1.250 €). Ημερομηνίες ως «6 Νοεμβρίου»."""

TOOLS = [
    {"name": "portfolio_summary", "eager_input_streaming": True,
     "description": "Σύνοψη χαρτοφυλακίου: πόσοι πελάτες/είδη σε κίνδυνο, αξία ανοιχτών προτάσεων, drafts στο ERP, ανά περιοχή/τύπο. "
                    "Προαιρετικά για έναν πωλητή (PRSN).",
     "input_schema": {"type": "object", "properties": {"salesman": {"type": "integer", "description": "PRSN πωλητή, π.χ. 105"}}}},
    {"name": "at_risk", "eager_input_streaming": True,
     "description": "Ζεύγη πελάτη × είδους που εξαντλούνται μέσα σε `days` μέρες (1–14), ταξινομημένα κατά ημερομηνία. "
                    "Φίλτρα: πωλητής, κατηγορία είδους (π.χ. Νερά, Μπύρες, Καφές, Αναψυκτικά), περιοχή, τύπος πελάτη, λέξη στο όνομα είδους.",
     "input_schema": {"type": "object", "properties": {
         "days": {"type": "integer"}, "salesman": {"type": "integer"}, "category": {"type": "string"},
         "area": {"type": "string"}, "customer_type": {"type": "string"}, "item_query": {"type": "string"}}}},
    {"name": "search_customers", "eager_input_streaming": True,
     "description": "Αναζήτηση πελάτη με όνομα, πόλη ή κωδικό. Επιστρέφει TRDR, τύπο, περιοχή, πωλητή, αν έχει πρόταση και την αξία της.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "customer_details", "eager_input_streaming": True,
     "description": "Όλα για έναν πελάτη: στοιχεία, πρόβλεψη για κάθε είδος, και η προτεινόμενη παραγγελία με τα στοιχεία που τη στηρίζουν "
                    "(ρυθμός κατανάλωσης, τελευταία παραλαβή, κύκλος αγορών, εποχικότητα, προσφορές).",
     "input_schema": {"type": "object", "properties": {"trdr": {"type": "integer"}}, "required": ["trdr"]}},
    {"name": "model_accuracy", "eager_input_streaming": True,
     "description": "Πόσο ακριβές είναι το μοντέλο πρόβλεψης (backtest): μέσο λάθος σε μέρες, % εντός ±3/±7, σύγκριση με baseline.",
     "input_schema": {"type": "object", "properties": {}}},
]

TOOL_LABELS = {
    "portfolio_summary": "Σύνοψη χαρτοφυλακίου",
    "at_risk": "Ψάχνω είδη σε κίνδυνο",
    "search_customers": "Αναζήτηση πελάτη",
    "customer_details": "Στοιχεία πελάτη",
    "model_accuracy": "Ακρίβεια μοντέλου",
}


class Data:
    """Read-only πρόσβαση στα δεδομένα του API (δίνεται από το main για να μην υπάρχει κυκλικό import)."""

    def __init__(self, suggestions: Callable[[], list], forecasts: Callable[[], list], customers: Callable[[], dict],
                 evaluation: Callable[[], dict], salesmen: Callable[[], dict]):
        self.suggestions, self.forecasts, self.customers, self.evaluation, self.salesmen = (
            suggestions, forecasts, customers, evaluation, salesmen)


# ---------------------------------------------------------------- εργαλεία
def _as_int(v):
    try:
        return int(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def run_tool(d: Data, name: str, args: dict) -> dict:
    args = args if isinstance(args, dict) else {}
    sugs = d.suggestions()
    cust = d.customers()
    names = d.salesmen()
    if name == "portfolio_summary":
        sm = _as_int(args.get("salesman"))
        mine = [s for s in sugs if sm is None or s["SALESMAN"] == sm]
        open_ = [s for s in mine if s["status"] not in ("draft_created", "cancelled")]
        risk7 = [f for f in d.forecasts() if f["days_left"] is not None and f["days_left"] <= 7
                 and (sm is None or cust[f["TRDR"]]["SALESMAN"] == sm)]
        by = lambda key: {k: sum(1 for s in open_ if s[key] == k) for k in sorted({s[key] for s in open_})}
        return {"salesman": names.get(sm) if sm else "όλοι", "customers_with_proposal": len(mine),
                "open_proposals": len(open_), "open_value_eur": round(sum(s.get("VALUE", 0) for s in open_)),
                "drafts_in_erp": sum(1 for s in mine if s["status"] == "draft_created"),
                "items_depleting_within_7_days": len(risk7),
                "customers_depleting_within_7_days": len({f["TRDR"] for f in risk7}),
                "open_by_area": by("AREA"), "open_by_customer_type": by("CUSTOMER_CATEGORY"),
                "most_urgent": [{"customer": s["CUSTOMER_NAME"], "trdr": s["TRDR"], "id": s["id"],
                                 "first_depletion": s["LINES"][0]["PREDICTED_DEPLETION_DATE"],
                                 "delivery": s["SUGGESTED_DELIVERY_DATE"], "value_eur": round(s.get("VALUE", 0))}
                                for s in sorted(open_, key=lambda s: (s["LINES"][0]["PREDICTED_DEPLETION_DATE"], -s.get("VALUE", 0)))[:6]]}
    if name == "at_risk":
        days = max(1, min(14, _as_int(args.get("days")) or 7))
        sm, cat, area, ctype = _as_int(args.get("salesman")), args.get("category"), args.get("area"), args.get("customer_type")
        q = (args.get("item_query") or "").lower()
        sug_by = {s["TRDR"]: s for s in sugs}
        rows = []
        for f in d.forecasts():
            c = cust[f["TRDR"]]
            if f["days_left"] is None or f["days_left"] > days: continue
            if sm is not None and c["SALESMAN"] != sm: continue
            if cat and cat.lower() not in (f.get("CATEGORY") or "").lower(): continue
            if area and area.lower() not in c["AREA"].lower(): continue
            if ctype and ctype.lower() not in c["TRDCATEGORY"].lower(): continue
            if q and q not in f["ITEM_NAME"].lower(): continue
            s = sug_by.get(f["TRDR"])
            line = next((l for l in s["LINES"] if l["MTRL"] == f["MTRL"]), None) if s else None
            rows.append({"customer": c["NAME"], "trdr": f["TRDR"], "item": f["ITEM_NAME"], "category": f.get("CATEGORY"),
                         "depletion": f["PREDICTED_DEPLETION_DATE"], "days_left": f["days_left"],
                         "suggested_qty": f"{line['QTY1']} {line['UNIT']}" if line else None,
                         "suggestion_id": s["id"] if s else None})
        rows.sort(key=lambda r: (r["depletion"], r["customer"]))
        return {"days": days, "total": len(rows), "customers": len({r["trdr"] for r in rows}), "rows": rows[:40]}
    if name == "search_customers":
        q = (args.get("query") or "").lower().strip()
        sug_by = {s["TRDR"]: s for s in sugs}
        hits = [c for c in cust.values() if q and q in f"{c['NAME']} {c['CITY']} {c['AREA']} {c['CODE']}".lower()][:10]
        return {"results": [{"trdr": int(c["TRDR"]), "name": c["NAME"], "type": c["TRDCATEGORY"], "city": c["CITY"],
                             "area": c["AREA"], "salesman": names.get(int(c["SALESMAN"])),
                             "has_proposal": int(c["TRDR"]) in sug_by,
                             "proposal_value_eur": round(sug_by[int(c["TRDR"])].get("VALUE", 0)) if int(c["TRDR"]) in sug_by else None}
                            for c in hits]}
    if name == "customer_details":
        t = _as_int(args.get("trdr"))
        if t not in cust:
            return {"error": "δεν βρέθηκε πελάτης με αυτό το TRDR"}
        c = cust[t]
        s = next((x for x in sugs if x["TRDR"] == t), None)
        fc = sorted([f for f in d.forecasts() if f["TRDR"] == t], key=lambda f: f["days_left"] if f["days_left"] is not None else 999)
        return {"customer": {"trdr": t, "name": c["NAME"], "type": c["TRDCATEGORY"], "city": c["CITY"], "area": c["AREA"],
                             "salesman": names.get(int(c["SALESMAN"])), "new_customer_since": c["INSDATE"] if c["INSDATE"] >= "2026-01-01" else None},
                "forecasts": [{"item": f["ITEM_NAME"], "depletion": f["PREDICTED_DEPLETION_DATE"] or "καμία σε 90 μέρες",
                               "days_left": f["days_left"]} for f in fc],
                "proposal": None if not s else {
                    "id": s["id"], "status": s["status"], "delivery": s["SUGGESTED_DELIVERY_DATE"], "value_eur": round(s.get("VALUE", 0)),
                    "erp_draft_id": s.get("erp_draft_id"),
                    "lines": [{**_line(l), "αξία_€": l.get("LINE_VALUE")} for l in s["LINES"]]}}
    if name == "model_accuracy":
        ev = d.evaluation()
        return {"method": ev.get("source"), "cutoffs": ev.get("cutoffs"), "current_model": ev.get("default_model"),
                "rows": ev.get("rows"), "coverage": ev.get("coverage"), "revival_reference": ev.get("readme_reference")}
    return {"error": f"άγνωστο εργαλείο {name}"}


# ---------------------------------------------------------------- συνομιλία (SSE)
def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def chat_stream(d: Data, history: list[dict], salesman: int | None) -> Iterator[str]:
    client = _get_client()
    if client is None:
        yield _sse({"type": "error", "message": "Ο AI βοηθός δεν είναι διαθέσιμος (λείπει ANTHROPIC_API_KEY)."})
        return
    msgs = [{"role": m["role"], "content": str(m["content"])[:4000]} for m in history[-12:]
            if m.get("role") in ("user", "assistant") and m.get("content")]
    if not msgs or msgs[-1]["role"] != "user":
        yield _sse({"type": "error", "message": "Κενή ερώτηση."}); return
    system = SYSTEM + (f"\nΟ χρήστης είναι ο πωλητής {d.salesmen().get(salesman)} (PRSN {salesman}). "
                       f"Εκτός αν ζητήσει κάτι άλλο, εννοεί τους δικούς του πελάτες." if salesman in d.salesmen() else "")
    try:
        for _ in range(MAX_TURNS):
            with client.beta.messages.stream(
                model=MODEL, max_tokens=4000, system=system, tools=TOOLS, messages=msgs,
                output_config={"effort": "low"}, **FALLBACK,
            ) as stream:
                for event in stream:
                    if event.type == "text":
                        yield _sse({"type": "text", "delta": event.text})
                resp = stream.get_final_message()
            tool_uses = [b for b in resp.content if b.type == "tool_use"]
            if resp.stop_reason == "refusal":
                yield _sse({"type": "error", "message": "Δεν μπορώ να απαντήσω σε αυτό."}); return
            if not tool_uses or resp.stop_reason == "max_tokens":
                yield _sse({"type": "done"}); return
            msgs.append({"role": "assistant", "content": resp.content})
            results = []
            for b in tool_uses:
                yield _sse({"type": "tool", "name": b.name, "label": TOOL_LABELS.get(b.name, b.name), "input": b.input})
                if not isinstance(b.input, dict):        # eager streaming: έλεγχος πριν την εκτέλεση
                    results.append({"type": "tool_result", "tool_use_id": b.id, "is_error": True, "content": "INVALID_JSON"})
                    continue
                out = run_tool(d, b.name, b.input)
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(out, ensure_ascii=False)})
            msgs.append({"role": "user", "content": results})
        yield _sse({"type": "done"})
    except anthropic.APIConnectionError:
        yield _sse({"type": "error", "message": "Δεν υπάρχει σύνδεση με το AI. Δοκίμασε ξανά."})
    except anthropic.RateLimitError:
        yield _sse({"type": "error", "message": "Πολλά αιτήματα στο AI — δοκίμασε σε λίγο."})
    except anthropic.APIStatusError as e:
        log.warning("assistant error %s: %s", e.status_code, e.message)
        yield _sse({"type": "error", "message": f"Σφάλμα AI ({e.status_code})."})
    except (anthropic.AnthropicError, TypeError) as e:
        log.warning("assistant unavailable: %s", e)
        yield _sse({"type": "error", "message": "Ο AI βοηθός δεν είναι διαθέσιμος."})


# ---------------------------------------------------------------- briefing & μήνυμα πελάτη
def _complete(system: str, payload: dict, max_tokens: int = 1200, attempts: int = 2) -> str | None:
    client = _get_client()
    if client is None:
        return None
    for i in range(attempts):                     # μία επιπλέον προσπάθεια πριν το template (π.χ. προσωρινό 529)
        try:
            r = client.beta.messages.create(model=MODEL, max_tokens=max_tokens, system=system, output_config={"effort": "low"},
                                            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}], **FALLBACK)
            if r.stop_reason == "refusal":
                return None
            text = "".join(b.text for b in r.content if b.type == "text").strip()
            if text:
                return text
        except TypeError as e:                    # χωρίς credentials
            log.warning("LLM unavailable: %s", e)
            return None
        except anthropic.AnthropicError as e:
            log.warning("LLM attempt %d failed: %s", i + 1, e)
    return None


BRIEFING_SYSTEM = """Γράφεις το πρωινό briefing ενός πωλητή χονδρεμπορίου, στα ελληνικά, ΜΟΝΟ από το JSON.
Μορφή: μία πρόταση χαιρετισμού με το μικρό του όνομα και το συνολικό εύρος (πελάτες, αξία), μετά 3 κουκκίδες «- » με τις
προτεραιότητες της ημέρας (πελάτης ως link [Όνομα](/customers/TRDR), τι τελειώνει πότε, αξία), και μία τελευταία σύντομη πρόταση
με πρακτική συμβουλή που βγαίνει από τα δεδομένα. Ως 110 λέξεις. Μην επινοείς αριθμούς. Ποσά «1.250 €», ημερομηνίες «6 Νοεμβρίου»."""

MESSAGE_SYSTEM = """Γράφεις μήνυμα από τον πωλητή της DEMO ΔΙΑΝΟΜΕΣ προς τον πελάτη του, στα ελληνικά, φιλικά και επαγγελματικά.
Σκοπός: να του πει ότι, με βάση τις παραγγελίες του, κάποια είδη μάλλον τελειώνουν σύντομα, και να προτείνει παράδοση.
ΜΟΝΟ στοιχεία από το JSON (είδη, ποσότητες, ημερομηνία παράδοσης). Μην αναφέρεις «μοντέλο», «AI», τιμές ή εσωτερικούς κωδικούς.
Αν υπάρχει μελλοντική προσφορά για είδος του, ανέφερέ τη σύντομα ως ευκαιρία.
- channel=sms: ως 320 χαρακτήρες, χωρίς χαιρετισμό τύπου «Αγαπητέ», τελειώνει με ερώτηση επιβεβαίωσης.
- channel=email: γραμμή «Θέμα: …», κενή γραμμή, σύντομο κείμενο με λίστα ειδών «- », υπογραφή με το όνομα του πωλητή."""


def briefing(d: Data, salesman: int) -> dict:
    summary = run_tool(d, "portfolio_summary", {"salesman": salesman})
    text = _complete(BRIEFING_SYSTEM, summary)
    if text:
        return {"text": text, "source": "llm", "data": summary}
    first = (summary["salesman"] or "").split(" ")[0]
    lines = "\n".join(f"- [{m['customer']}](/customers/{m['trdr']}): τελειώνει {gr_date(m['first_depletion'])}, "
                      f"παράδοση {gr_date(m['delivery'])}, {m['value_eur']:,} €".replace(",", ".") for m in summary["most_urgent"][:3])
    text = (f"Καλημέρα {first}! Έχεις {summary['open_proposals']} ανοιχτές προτάσεις αξίας "
            f"{summary['open_value_eur']:,} €.".replace(",", ".") + f"\n{lines}")
    return {"text": text, "source": "template", "data": summary}


def customer_message(s: dict, channel: str) -> dict:
    payload = {"channel": channel, "customer": s["CUSTOMER_NAME"], "salesman": s["SALESMAN_NAME"],
               "delivery": s["SUGGESTED_DELIVERY_DATE"],
               "items": [{"είδος": l["ITEM_NAME"], "ποσότητα": l["QTY1"], "μονάδα": l["UNIT"],
                          "τελειώνει_περίπου": l["PREDICTED_DEPLETION_DATE"],
                          "προσφορά": (l["evidence"].get("promo") or {}).get("name")} for l in s["LINES"]]}
    text = _complete(MESSAGE_SYSTEM, payload, 900)
    if text:
        return {"text": text, "source": "llm", "channel": channel}
    items = ", ".join(f"{l['ITEM_NAME']} ({l['QTY1']} {l['UNIT']})" for l in s["LINES"][:4])
    text = (f"Καλησπέρα από τη DEMO ΔΙΑΝΟΜΕΣ! Βλέπουμε ότι σύντομα θα χρειαστείτε: {items}. "
            f"Να τα φέρουμε {gr_date(s['SUGGESTED_DELIVERY_DATE'])}; — {s['SALESMAN_NAME']}")
    return {"text": text, "source": "template", "channel": channel}
