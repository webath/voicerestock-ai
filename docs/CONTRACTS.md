# Contracts — το μόνο σημείο επαφής Δημήτρη ↔ Νίκου

> Αλλαγές εδώ **μόνο με PR** που ενημερώνει ταυτόχρονα το `fixtures/suggestions.sample.json`
> και το `scripts/mock_app_api.py`, ώστε mock και πραγματικό API να μένουν ίδια.

## Services & ports

| Service | Owner | Port | Τι κάνει |
|---|---|---|---|
| Mock ERP (`team_pack/mock_erp_server.py`) | δοσμένο | 8080 | Δεδομένα + `POST /api/draft-orders` |
| App API (`apps/api`, FastAPI) | Δημήτρης | 8000 | Forecasts, suggestions, state, audit, ERP writes |
| Mock App API (`scripts/mock_app_api.py`) | Νίκος (dev only) | 8000 | Ίδια endpoints πάνω στο fixture — για όσο δεν υπάρχει το πραγματικό |
| Voice (`apps/voice`, Node/TS) | Νίκος | 8100 | Twilio webhooks, WebSocket, LLM dialogue |
| Web (`apps/web`, Next.js) | Νίκος | 3000 | Dashboard |

```
Twilio ⇄ Voice :8100 ──HTTP──▶ App API :8000 ──HTTP──▶ Mock ERP :8080
                                   ▲
                        Web :3000 ─┘
```

**Κανόνας ασφαλείας:** το Voice δεν γράφει ποτέ στο ERP. Μόνο το App API κάνει `POST /api/draft-orders`,
και μόνο με έγκυρο `confirmation_token`.

---

## Αντικείμενα

### `Suggestion` (μία πρόταση παραγγελίας ανά πελάτη)

Είναι υπερσύνολο του `sample_suggested_order.json` — τα κεφαλαία πεδία πάνε αυτούσια στο ERP.

```jsonc
{
  "id": "SUG-1004-001",            // σταθερό id
  "version": 1,                     // +1 σε κάθε αλλαγή ποσότητας
  "status": "proposed",             // βλ. state machine
  "urgency": "high",                // high: εξάντληση ≤ 7 μέρες, medium: ≤ 14, low: αλλιώς
  "TRDR": 1004,
  "CUSTOMER_CODE": "30.00.0004",
  "CUSTOMER_NAME": "Mini Market Οικονομικό Μ.Ε.Π.Ε.",
  "CUSTOMER_CATEGORY": "Mini Market",
  "AREA": "Θεσσαλονίκη",
  "SALESMAN": 105,
  "SALESMAN_NAME": "Στέλιος Παπαγεωργίου",
  "SUGGESTED_DELIVERY_DATE": "2026-11-03",   // εργάσιμη, όχι Κυριακή/αργία, πριν την 1η εξάντληση
  "REASON": "Το Ice tea λεμόνι τελειώνει στις 6/11",
  "LINES": [ /* SuggestionLine[] */ ],
  "erp_draft_id": null,             // γεμίζει μετά το create-draft
  "updated_at": "2026-11-01T09:00:00Z"
}
```

### `SuggestionLine`

```jsonc
{
  "MTRL": 5016,
  "ITEM_CODE": "10.02.008",
  "ITEM_NAME": "Ice tea λεμόνι 500ml κιβ. 12τεμ",
  "UNIT": "ΚΙΒ",                    // ΚΙΒ | ΤΕΜ
  "QTY1": 4,                        // τρέχουσα προτεινόμενη ποσότητα (ακέραιος > 0)
  "QTY_RECOMMENDED": 4,             // αυτό που πρότεινε το μοντέλο (δεν αλλάζει)
  "QTY_MIN": 1,                     // όρια που επιβάλλει το API στις αλλαγές
  "QTY_MAX": 12,
  "PREDICTED_DEPLETION_DATE": "2026-11-06",
  "CONFIDENCE": 0.8,                // από το μοντέλο, ΟΧΙ από LLM
  "evidence": { /* Evidence */ }
}
```

### `Evidence` (ό,τι επιτρέπεται να πει ο agent/LLM)

```jsonc
{
  "model_version": "hybrid_0.7@2026-11-06",
  "burn_rate_per_day": 0.57,        // μελλοντικός ρυθμός (μονάδες MTRUNIT1/μέρα)
  "burn_rate_recent_per_day": 0.74, // ρυθμός τελευταίων 90 ημερών
  "last_purchase_date": "2026-10-24",
  "last_purchase_qty": 4,
  "avg_interval_days": 7.1,         // μέσο διάστημα μεταξύ αγορών
  "purchases_count": 98,
  "est_stock_at_cutoff": 2.9,
  "seasonal_multiplier": 0.85,      // null αν δεν εφαρμόστηκε
  "promo": null,                    // ή {"name": "...", "disc_prc": 10, "from": "2026-11-09", "to": "2026-11-27"}
  "cold_start": false,
  "peer_group": null,               // π.χ. "Καφέ-Μπαρ / Αθήνα" όταν cold_start
  "factors": [
    {"name": "seasonality", "impact_days": 1.2, "source": "ίδια περίοδος πέρσι × φετινή τάση"},
    {"name": "purchase_cycle", "impact_days": null, "source": "αγοράζει κάθε ~14 μέρες"}
  ],
  "warnings": []                    // π.χ. "λίγο ιστορικό", "ασταθής ρυθμός"
}
```

Αν ένα πεδίο είναι `null`, ο agent λέει «δεν υπάρχει επαρκής ένδειξη» — **δεν** επινοεί.

### `Call` (για τη σελίδα Voice Operations)

```jsonc
{
  "call_sid": "CA...",
  "salesman": 105,
  "suggestion_ids": ["SUG-1004-001"],
  "status": "discussing",           // queued|dialing|connected|greeted|discussing|confirming|posting_draft|draft_created|failed|cancelled|ended
  "started_at": "...", "ended_at": null,
  "transcript": [{"role": "agent", "text": "...", "at": "..."}],
  "erp_draft_ids": []
}
```

---

## State machine της Suggestion

```
proposed ──(qty change)──▶ modified ──┐
   │                                  │
   └──────────(confirm)───────────────┴─▶ confirmed ──(create-draft)──▶ posting ──▶ draft_created
                                                                          └──────▶ failed (retryable)
proposed|modified ──▶ cancelled
```

- Αλλαγή ποσότητας μετά από `confirmed` → γυρνάει σε `modified`, ακυρώνει το token.
- `create-draft` δεύτερη φορά με το ίδιο `idempotency_key` → επιστρέφει το **ίδιο** `erp_draft_id`, δεν ξαναγράφει.

---

## Endpoints του App API (`http://localhost:8000`)

Όλα JSON. Σφάλματα: `{"error": "code", "message": "..."}` με 400/404/409.
Κάθε write δέχεται header `X-Actor` (π.χ. `salesman:105` ή `voice:CA123`) και γράφεται στο audit.

| Method | Path | Body | Απάντηση |
|---|---|---|---|
| GET | `/api/health` | – | `{"ok": true}` |
| GET | `/api/salesmen` | – | `[{"PRSN":101,"NAME":"...","phone":"+30..."}]` (phone από `.env`, για demo) |
| GET | `/api/risk?salesman=105&limit=20` | – | `[{TRDR, CUSTOMER_NAME, CUSTOMER_CATEGORY, AREA, SALESMAN, MTRL, ITEM_NAME, CATEGORY, PREDICTED_DEPLETION_DATE, days_left, CONFIDENCE, urgency, suggestion_id}]` — μόνο εξάντληση ≤ 14 μέρες, κατά ημερομηνία |
| GET | `/api/suggestions?salesman=105&status=proposed` | – | `Suggestion[]` ταξινομημένα κατά urgency |
| GET | `/api/suggestions/{id}` | – | `Suggestion` |
| POST | `/api/suggestions/{id}/lines/{mtrl}/quantity` | `{"qty": 15, "version": 1}` | `Suggestion` (version+1). 409 αν λάθος version, 400 εκτός `QTY_MIN..QTY_MAX` |
| POST | `/api/suggestions/{id}/confirm` | `{"version": 2}` | `{"confirmation_token": "...", "snapshot": Suggestion}` |
| POST | `/api/suggestions/{id}/create-draft` | `{"confirmation_token": "...", "idempotency_key": "..."}` | `{"erp_draft_id": "DRAFT-...", "status": "draft_created"}` |
| POST | `/api/suggestions/{id}/cancel` | `{}` | `Suggestion` |
| GET | `/api/forecasts?trdr=1004` | – | `[{TRDR, MTRL, ITEM_NAME, CATEGORY, PREDICTED_DEPLETION_DATE, days_left, CONFIDENCE, urgency}]` (`urgency: "none"` = καμία εξάντληση σε 90 μέρες) — όλα τα target ζεύγη του πελάτη (και όχι-at-risk) |
| GET | `/api/customers/{trdr}/history?mtrl=5016` | – | `{"TRDR", "items": [{"MTRL", "ITEM_NAME", "points": [{"date": "2026-10-24", "qty": 4}]}]}` — καθαρή ποσότητα ανά μέρα (πιστωτικά αρνητικά, χωρίς ακυρωμένα/μεταφορικά). `mtrl` προαιρετικό |
| GET | `/api/suggestions/{id}/explanation` | – | `{"text": "...", "source": "llm"\|"template", "model": "...", "grounded_on": [...]}` — ελληνική εξήγηση **μόνο** από το evidence |
| GET | `/api/evaluation` | – | `{"source": "local_backtest", "cutoffs": [...], "rows": [{"model", "mae", "within_3", "within_7", "at_risk_precision", "at_risk_recall"}]}` |
| POST | `/api/calls/events` | `{"call_sid","type","status?","text?","role?","suggestion_id?","erp_draft_id?"}` | `{"ok": true}` — το Voice στέλνει εδώ ό,τι συμβαίνει |
| GET | `/api/calls` | – | `Call[]` (πιο πρόσφατη πρώτη) |
| GET | `/api/audit?limit=200` | – | `[{at, actor, action, suggestion_id, outcome}]` |
| POST | `/api/admin/reset` | – | `{"ok": true, "suggestions": 124}` — ξαναφορτώνει τις προτάσεις (demo) |

Το `create-draft` στο App API μετατρέπει τη Suggestion σε payload ERP:
`{TRDR, CUSTOMER_CODE, SALESMAN, SUGGESTED_DELIVERY_DATE, REASON, LINES:[{MTRL, ITEM_CODE, QTY1, PREDICTED_DEPLETION_DATE, CONFIDENCE}]}`
και κάνει `POST http://localhost:8080/api/draft-orders`. Μόνο αν το ERP απαντήσει 201 γυρνάει επιτυχία.

## Endpoints του Voice (`http://localhost:8100`) — Νίκος

| Method | Path | Ποιος το καλεί |
|---|---|---|
| POST | `/voice/calls` `{"salesman": 105}` | Dashboard (κουμπί «Κάλεσε») |
| POST | `/voice/twiml` | Twilio |
| POST | `/voice/status` | Twilio (signature verified) |
| WS | `/voice/ws` | Twilio ConversationRelay |
| GET | `/voice/health` | – |
