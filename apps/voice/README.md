# apps/voice — Voice agent — Νίκος

Ο agent **καλεί τον πωλητή** στο κινητό, του λέει στα ελληνικά ποιοι πελάτες του κινδυνεύουν να ξεμείνουν,
εξηγεί γιατί (μόνο από το `evidence`), δέχεται αλλαγές ποσότητας και, μετά από **ρητό «ναι» σε ακριβή
περίληψη**, δημιουργεί **ένα** DRAFT στο ERP μέσω του App API.

> Αντί για Twilio (`docs/VOICE.md`) χρησιμοποιούμε τον **υπάρχοντα, δοκιμασμένο στα ελληνικά** voice agent του Νίκου
> στο VPS: Pipecat + LiveKit SIP → FreePBX → Intertelecom, φωνή OpenAI `gpt-live-1`, εργαλεία μέσω Gemini backend.

## Αρχιτεκτονική

```
dashboard (laptop :3000) ──POST /voice/calls──▶ [tunnel] ──▶ VPS 127.0.0.1:8100  bot_voicerestock.py
                                                                   │  gpt-live-1 (φωνή) ⇄ Gemini (εργαλεία)
                                                                   │  vr_core.CallSession (κανόνες ασφαλείας)
                                                                   ▼
App API (laptop :8000) ◀──[reverse tunnel, VPS 127.0.0.1:18000]────┘
     └──▶ Mock ERP :8080 (POST /api/draft-orders)
LiveKit SIP ──▶ FreePBX ──▶ Intertelecom ──▶ κινητό πωλητή
```

| Αρχείο | Τι κάνει |
|---|---|
| `vr_core.py` | Χωρίς pipecat: ελληνικές λέξεις για ποσότητες/ημερομηνίες, κείμενα από το evidence, `CallSession` (εργαλεία + κανόνες) |
| `bot_voicerestock.py` | Pipecat/LiveKit: εξερχόμενη/εισερχόμενη κλήση, prompts, HTTP `POST /voice/calls`, live transcript → `/api/calls/events` |
| `tests/test_core.py` | Tests πάνω στους πραγματικούς mock ERP + mock App API (exactly-once draft, όρια, ιδιοκτησία, «15 vs 50») |
| `deploy/` | `push.sh` (laptop→VPS), `deploy.sh` / `rollback.sh` (στο VPS), `tunnel.sh` (laptop), Dockerfile, compose override |

## Κανόνες ασφαλείας (υλοποιούνται στον server, όχι στο prompt)

- Το LLM δίνει μόνο `suggestion_id`, `mtrl`, `qty`. Ο server ελέγχει ότι η πρόταση ανήκει **στον πωλητή της κλήσης**.
- Ποσότητα: ακέραιος μέσα σε `QTY_MIN..QTY_MAX`· πάνω από **2× την πρόταση** → ο agent ξαναρωτά τον αριθμό.
- Δύο βήματα: `prepare_order` (διαβάζει την ακριβή περίληψη) → `place_draft_order` (μόνο μετά από «ναι»).
  Αν αλλάξει κάτι ανάμεσα, το draft **δεν** γίνεται.
- `confirmation_token` μένει στον server· `idempotency_key = {call}:{suggestion}:v{version}` → ποτέ διπλό draft.
- «Έγινε» λέγεται μόνο όταν το App API επιστρέψει `erp_draft_id`.
- Allowlist αριθμών, ώρες ησυχίας, AI disclosure, τηλεφωνητής/άλλος άνθρωπος → καμία παραγγελία.
- Ποσότητες, ημερομηνίες και κωδικοί λέγονται με **λέξεις** (το φωνητικό μοντέλο εκφωνεί λάθος τα ψηφία).

## Εντολές

```bash
python3 -m unittest discover -s apps/voice/tests -v          # tests (Python 3.9+, χωρίς εξαρτήσεις)

# laptop
python3 team_pack/mock_erp_server.py                          # :8080
python3 scripts/mock_app_api.py                               # :8000
apps/voice/deploy/tunnel.sh                                   # μένει ανοιχτό
apps/voice/deploy/push.sh                                     # ανεβάζει κώδικα στο VPS (δεν αλλάζει τον agent)

# VPS (μία φορά: cp deploy/voicerestock.env.example /root/voicerestock/voicerestock.env και συμπλήρωσε)
/root/voicerestock/deploy/deploy.sh                           # παγώνει SafeVoice → σηκώνει VoiceRestock
/root/voicerestock/deploy/rollback.sh                         # πίσω στον SafeVoice

# κλήση
curl -XPOST localhost:8100/voice/calls -H 'content-type: application/json' -d '{"salesman":105}'
curl localhost:8100/voice/health
```

Endpoints: `POST /voice/calls {"salesman": N}` → `202 {"call_sid", "status": "queued"}` (409 αν busy / ώρες ησυχίας /
καμία πρόταση, 403 αν ο αριθμός δεν είναι στο allowlist), `GET /voice/health`.
