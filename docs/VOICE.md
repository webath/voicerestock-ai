# Voice Agent — brief για τον Νίκο

Ό,τι χρειάζεσαι για να χτίσεις το `apps/voice` χωρίς να περιμένεις τον Δημήτρη.
Πλήρες σκεπτικό: `docs/challenge/VoiceRestock_Master_Spec.pdf` §7–8.

## Τι κάνει (σε μία πρόταση)

Ο agent **καλεί** τον Account Manager (πωλητή), του λέει στα ελληνικά ποιοι πελάτες του κινδυνεύουν να ξεμείνουν,
εξηγεί **γιατί** (μόνο από το `evidence`), δέχεται αλλαγές ποσότητας («κάν' τα 15»), ζητάει ρητή επιβεβαίωση,
και δημιουργεί **draft** παραγγελία στο ERP μέσω του App API.

## Ξεκίνα τώρα, χωρίς backend

```bash
python3 team_pack/mock_erp_server.py          # :8080 (πραγματικό mock ERP)
python3 scripts/mock_app_api.py               # :8000 (ψεύτικο App API πάνω στο fixture)
curl localhost:8000/api/suggestions?salesman=105
```

Το `mock_app_api.py` υλοποιεί τα **ίδια** endpoints με το `docs/CONTRACTS.md` (quantity, confirm, create-draft, calls/events)
και γράφει **πραγματικά** drafts στο mock ERP. Όταν ο Δημήτρης έχει το αληθινό API (checkpoint Σάββατο 14:00),
απλά σταματάς το mock — ίδιο port, ίδια σχήματα.

## Stack (πρόταση)

- Node 20+ / TypeScript / Fastify + `@fastify/websocket`, `twilio` SDK
- **Transport — Plan A:** Twilio Programmable Voice → `<Connect><ConversationRelay language="el-GR" ...>` → WebSocket στο `/voice/ws`.
  Το Twilio κάνει STT/TTS· εσύ λαμβάνεις κείμενο (`prompt` events) και στέλνεις κείμενο (`text` tokens, streaming).
  Επιβεβαίωσε στο spike ποιος STT/TTS provider δίνει καλά ελληνικά (π.χ. Google / ElevenLabs) — **μην το υποθέσεις, δοκίμασέ το**.
- **Plan B (αν το A δεν δουλεύει στα ελληνικά μέσα σε ~2 ώρες):** Twilio Media Streams + δικό σου realtime STT/TTS bridge.
- **Plan C (fallback για demo):** browser voice στο dashboard (μικρόφωνο → STT → ίδιο agent loop → TTS) + ηχογραφημένη κλήση.
  Η σκηνή της παρουσίασης μπορεί να μην έχει σήμα — έχε το C έτοιμο.
- **LLM:** Claude με tool use. Για χαμηλό latency στο τηλέφωνο: `claude-haiku-5-5`· αν θες καλύτερη κατανόηση: `claude-sonnet-5-5`.
  Streaming των tokens στο ConversationRelay για να μην ακούγεται σιωπή.
- Τοπικά webhooks: `ngrok http 8100` (ή cloudflared) → βάλε το URL στο `.env` (`VOICE_PUBLIC_URL`).

Προσοχή Twilio trial: καλεί μόνο **verified** αριθμούς και παίζει μήνυμα trial στην αρχή. Ενεργοποίησε Geo Permissions για Ελλάδα.

## Tools του LLM (typed, τίποτα άλλο)

Κάθε tool = ένα HTTP call στο App API. Το LLM **δεν** βλέπει ERP, SQL ή credentials.

| Tool | App API |
|---|---|
| `get_my_suggestions()` | `GET /api/suggestions?salesman={από την κλήση}` |
| `get_suggestion(id)` | `GET /api/suggestions/{id}` |
| `change_quantity(id, mtrl, qty)` | `POST /api/suggestions/{id}/lines/{mtrl}/quantity` |
| `confirm_order(id)` | `POST /api/suggestions/{id}/confirm` → κρατάς το token **στον server σου**, όχι στο LLM |
| `create_draft(id)` | `POST /api/suggestions/{id}/create-draft` — εκτελείται μόνο αν το state machine είναι `explicit_confirmation` |
| `get_draft_status(id)` | `GET /api/suggestions/{id}` → `erp_draft_id` |

Το `salesman` το ξέρει ο server από την κλήση (σε ποιον τηλεφώνησε) — **δεν** το δίνει το LLM. Έτσι ο πωλητής βλέπει μόνο τους δικούς του πελάτες.

## State machine κλήσης

```
queued → dialing → connected → greeted → discussing
   → quantity_modified? → explicit_confirmation → validated
   → posting_draft → draft_created | failed | cancelled
disconnected / timeout → ασφαλής έξοδος, κανένα νέο order αν δεν έχει ήδη γίνει POST
```

Στείλε κάθε μετάβαση + κάθε φράση (agent/χρήστη) στο `POST /api/calls/events` ώστε να φαίνεται live στο dashboard.

**Η σελίδα `/voice` του dashboard είναι έτοιμη** (Δημήτρης): ανανεώνεται κάθε 3", δείχνει βήματα (`dialing → connected → discussing → confirming → posting_draft → draft_created`), transcript (`role: "agent"` / `"user"`) και draft ids. Το κουμπί «Κάλεσε» κάνει `POST {VOICE_URL}/voice/calls {"salesman": 105}` — αυτό το endpoint είναι δικό σου.

## Κανόνες ασφαλείας (θα τους ψάξουν οι κριτές)

1. **AI disclosure** στην αρχή: «Γεια σας, είμαι ο ψηφιακός βοηθός της DEMO ΔΙΑΝΟΜΕΣ…»
2. **Διπλή επιβεβαίωση:** πριν από κάθε write ο agent διαβάζει την ακριβή περίληψη (πελάτης, είδος, ποσότητα, μονάδα, ημερομηνία παράδοσης)
   και περιμένει σαφές «ναι, επιβεβαιώνω». Ένα ασαφές «οκ» δεν αρκεί.
3. **Αριθμοί:** «δεκαπέντε» vs «πενήντα» — επανάλαβε τον αριθμό και ρώτα ξανά αν είναι εκτός `QTY_MIN..QTY_MAX` ή > 2× της πρότασης.
4. **Exactly-once:** `idempotency_key = {call_sid}:{suggestion_id}:{version}`. Διπλό webhook/retry δεν δημιουργεί δεύτερο draft.
5. **Ποτέ «έγινε» πριν απαντήσει το ERP** με `erp_draft_id`. Μετά το λες: «Το draft δημιουργήθηκε με κωδικό …».
6. Allowlist αριθμών (`VOICE_ALLOWED_NUMBERS`), quiet hours (π.χ. 09:00–20:00), επαλήθευση Twilio signature στα webhooks.
7. Voicemail / άλλος σηκώνει / κλείνει η γραμμή → καμία παραγγελία.
8. Ο agent δεν προτείνει ποτέ προϊόν που δεν είναι στη Suggestion. Αν τον ρωτήσουν κάτι που δεν ξέρει: «δεν μπορώ να το επιβεβαιώσω, δείτε το στο dashboard».

## Παράδειγμα διαλόγου (στόχος για το demo)

> **AI:** Καλησπέρα κύριε Παπαγεωργίου, είμαι ο ψηφιακός βοηθός της DEMO ΔΙΑΝΟΜΕΣ. Έχετε 3 πελάτες που κινδυνεύουν να ξεμείνουν αυτή την εβδομάδα. Ο πιο επείγων είναι το Mini Market Οικονομικό: το Ice tea λεμόνι τελειώνει γύρω στις 6 Νοεμβρίου. Προτείνω 4 κιβώτια με παράδοση Τρίτη 3/11. Θέλετε να σας πω γιατί;
> **Πωλητής:** Ναι, γιατί τέσσερα;
> **AI:** Αγοράζει περίπου 4 κιβώτια κάθε εβδομάδα και η τελευταία παραλαβή ήταν στις 24/10. Τον Νοέμβριο η κατανάλωση πέφτει λίγο λόγω εποχής.
> **Πωλητής:** Κάν' τα έξι και φτιάξ' το.
> **AI:** Επιβεβαιώνετε draft για Mini Market Οικονομικό: Ice tea λεμόνι, **έξι κιβώτια**, παράδοση Τρίτη 3 Νοεμβρίου;
> **Πωλητής:** Ναι, επιβεβαιώνω.
> **AI:** Έγινε. Το ERP δημιούργησε draft με κωδικό DRAFT-…. Να πάμε στον επόμενο πελάτη;

## Acceptance (Definition of Done για το voice)

- [ ] Πραγματική κλήση σε allowlisted ελληνικό κινητό
- [ ] Ο πωλητής κάνει 2 αυθόρμητες ερωτήσεις και παίρνει σωστές (grounded) απαντήσεις
- [ ] «Βάλε 15 κιβώτια» → ακούει την ακριβή περίληψη → επιβεβαιώνει → **ακριβώς ένα** `DRAFT-*.json` στο `team_pack/draft_orders/`
- [ ] Λάθος πωλητής / voicemail / κλείσιμο γραμμής / διπλό webhook → κανένα draft
- [ ] Η σελίδα Voice Operations δείχνει live status + transcript + draft id
- [ ] Ηχογραφημένο fallback έτοιμο για την παρουσίαση
