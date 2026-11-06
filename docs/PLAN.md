# Πλάνο υλοποίησης & μοιρασιά δουλειάς

**Ομάδα:** Δημήτρης (data & backend) · Νίκος (dashboard & voice agent)
**Παρουσίαση:** Κυριακή 8/11, 15:00 · **Code freeze:** Κυριακή 13:00
**Χρόνος:** Παρασκευή 6/11 ~19:00 → Κυριακή 13:00 ≈ 30–34 ώρες ενεργής δουλειάς

---

## Η βασική αρχή προτεραιότητας

Οι βαθμοί είναι: **Technical 40% · Accuracy 30% · Business 20% · Innovation 10%**.
Άρα με αυτή τη σειρά σημαντικότητας:

1. `submission.csv` για **όλα** τα 1.975 ζεύγη (ζεύγος που λείπει = 60 μέρες λάθος). **Πρώτο πράγμα που βγαίνει, ήδη από Παρασκευή βράδυ.**
2. Σωστό header/lines handling + suggested orders που περνάνε από το `POST /api/draft-orders`.
3. Dashboard «At Risk» όπου ο Account Manager εγκρίνει παραγγελία.
4. Βελτίωση MAE (στόχος < 10 μέρες, baseline 16,1).
5. Voice agent (το «wow» του demo — αλλά **ποτέ** δεν πρέπει να μπλοκάρει τα 1–4).

## Η λογική της μοιρασιάς

Χωρίζουμε στο **HTTP API** (`docs/CONTRACTS.md`):

- **Δημήτρης = από τα δεδομένα μέχρι το API.** Ό,τι παράγει αριθμούς (forecast, ποσότητες, confidence, evidence) και ό,τι γράφει στο ERP.
- **Νίκος = ό,τι βλέπει ή ακούει ο χρήστης.** Dashboard και voice agent. Και τα δύο είναι *καταναλωτές* του ίδιου API.

Ο Νίκος δουλεύει από την πρώτη στιγμή πάνω σε **fixtures + mock API** (`fixtures/suggestions.sample.json`, `scripts/mock_app_api.py`)
και αλλάζει στο πραγματικό API στο checkpoint του Σαββάτου. Έτσι κανείς δεν περιμένει τον άλλον.

---

## Ποιος έχει τι (ownership)

| Περιοχή | Owner | Φάκελος |
|---|---|---|
| Ingestion, cleaning, features, forecast, backtest, submission | **Δημήτρης** | `services/forecast/` |
| Suggested orders (ποσότητα, ημ. παράδοσης, confidence, evidence) | **Δημήτρης** | `services/forecast/` |
| App API (suggestions, quantity, confirm, create-draft, history, evaluation, calls, audit) | **Δημήτρης** | `apps/api/` |
| LLM εξηγήσεις για το dashboard (grounded σε evidence) | **Δημήτρης** | `apps/api/` (`/explanation`) |
| Αποτελέσματα backtest | **Δημήτρης** | `docs/RESULTS.md` |
| Dashboard: όλες οι σελίδες (έτοιμες, glass theme) | **Δημήτρης** | `apps/web/` |
| Voice agent (Twilio, WS, STT/TTS, LLM dialogue, tools, state machine) | **Νίκος** | `apps/voice/` |
| Mock App API (κρατιέται ίδιο με τα contracts) | **Νίκος** | `scripts/mock_app_api.py` |
| Contracts (σχήματα JSON, endpoints) | **κοινό** — αλλαγή μόνο με PR & ok και από τους δύο | `docs/CONTRACTS.md`, `fixtures/` |
| Pitch / demo script | κοινό | `docs/DEMO.md` |

Κανόνας: **κανείς δεν αγγίζει φάκελο του άλλου** χωρίς να του το πει. Αν ο Νίκος χρειάζεται νέο πεδίο/endpoint → PR στο `docs/CONTRACTS.md`
+ fixture + mock, και ο Δημήτρης το υλοποιεί στο πραγματικό API.
Ούτε το dashboard ούτε το voice μιλάνε απευθείας με το mock ERP — μόνο με το App API.

---

## Σειρά υλοποίησης (timeline)

### Φάση 0 — Setup (Παρ 19:00–21:00)

**Κοινό (15')**: clone repo, διαβάστε `README.md`, `CLAUDE.md`, `docs/CONTRACTS.md`. Ξεκινήστε `python3 team_pack/mock_erp_server.py`.

**Δημήτρης**
- [x] Python env (`brew install uv` → `cd services/forecast && uv sync`)
- [x] `ingest.py`: φόρτωση SALDOC + MTRLINES, join σε FINDOC, κανόνες καθαρισμού (βλ. `docs/DATA_NOTES.md`), report με counts πριν/μετά από κάθε φίλτρο
- [x] Tests για τους κανόνες: 0 ακυρωμένα, πιστωτικά αρνητικά, free goods μέσα, μεταφορικά έξω

**Νίκος**
- [ ] Twilio λογαριασμός + αριθμός + **verified caller ID** του κινητού του (trial κλήσεις πάνε μόνο σε verified αριθμούς) + Geo permissions για Ελλάδα
- [ ] **Spike (το πιο ρισκαρισμένο κομμάτι όλου του project):** πραγματική εξερχόμενη κλήση στο κινητό με ConversationRelay, `language=el-GR`, που απλά απαντά «γεια». Επιβεβαίωση ότι STT και TTS δουλεύουν στα ελληνικά
- [ ] Αν το Greek ConversationRelay δεν δουλεύει μέσα σε ~2 ώρες → Plan B (βλ. `docs/VOICE.md`)
- [x] `apps/web`: Next.js 16, layout, πλοήγηση, client για το App API (`lib/api.ts`) — έτοιμο από τον Δημήτρη

### Φάση 1 — Πρώτο submission & βάσεις (Παρ 21:00–02:00)

**Δημήτρης**
- [x] Τοπικό **scorer** που αναπαράγει ακριβώς τον κανόνα βαθμολόγησης του README §7 (MAE, ±3, ±7, precision/recall At Risk)
- [x] **Backtest harness**: ψεύτικο cutoff (π.χ. 2026-08-01, 2026-05-02, 2025-11-01), «αληθινή» εξάντληση από τα πραγματικά δεδομένα μετά το cutoff
- [x] Baseline (μέσος ρυθμός 180 ημερών) → επιβεβαίωση ότι βγάζει ~16 μέρες MAE στο backtest
- [x] **`submissions/team_<όνομα>.csv` v1** με 1.975 γραμμές → commit. Από εδώ και πέρα έχουμε πάντα κάτι να παραδώσουμε

**Νίκος**
- [x] Σελίδα **At Risk** (Δημήτρης) (`GET /api/risk`, `GET /api/suggestions`) με φίλτρα πωλητή / κατηγορίας / περιοχής / urgency
- [ ] `apps/voice`: Node + TypeScript + Fastify, TwiML endpoint, WebSocket για ConversationRelay, LLM loop με tool calling πάνω στο mock
- [ ] Ο agent διαβάζει μια πρόταση από το fixture και την περιγράφει στα ελληνικά στο τηλέφωνο

### Φάση 2 — Καλύτερο μοντέλο, πραγματικό API, πλήρεις ροές (Σαβ 09:00–14:00)

**Δημήτρης**
- [ ] Μοντέλο v2: ανακατασκευή αποθέματος από τον κύκλο αγορών (βλ. «Ιδέες αλγορίθμου» παρακάτω)
- [x] Εποχικότητα (`seasonal_yoy` + `hybrid_0.6`, MAE backtest 3,78)
- [x] Προσφορές (απόθεμα, όχι κατανάλωση) και cold start από peers — `hybrid_0.7`, MAE backtest 3,63
- [x] Αργίες Χριστουγέννων: ελέγχθηκαν, δεν χρειάζεται διόρθωση (1/1.975 ζεύγη στο διάστημα)
- [x] `SUGGESTED_QTY` στο submission — κάθε βελτίωση στο backtest, γραμμή στο `docs/RESULTS.md`
- [x] `suggest.py`: Suggested Order ανά πελάτη (εργάσιμη παράδοση πριν την εξάντληση, ποσότητα, όρια, confidence, evidence) → `data/processed/suggestions.json` στο σχήμα του fixture
- [x] `apps/api` (FastAPI): όλα τα endpoints του `docs/CONTRACTS.md` με την ίδια συμπεριφορά με το mock (versions, tokens, idempotency), SQLite για state/audit

**Νίκος**
- [x] Σελίδα **Suggested Orders** (Δημήτρης): αλλαγή ποσότητας, «Έγκριση» (confirm → create-draft) → δείχνει το ERP draft id
- [ ] Voice: όλα τα tools, state machine κλήσης, διπλή προφορική επιβεβαίωση, εξήγηση **μόνο** από το `evidence`

### 🔗 Checkpoint integration (Σαβ 14:00)
> ✅ Το πραγματικό API είναι έτοιμο από Παρασκευή βράδυ: `./scripts/dev_backend.sh` (pipeline + ERP :8080 + API :8000). Ο Νίκος μπορεί να αλλάξει από το mock όποτε θέλει.
- Ο Δημήτρης έχει το πραγματικό API στο `:8000` με τα ίδια σχήματα με το fixture
- Ο Νίκος σταματάει το mock → dashboard και voice δουλεύουν με πραγματικές προβλέψεις
- End-to-end: έγκριση από dashboard **και** από κλήση → `team_pack/draft_orders/DRAFT-*.json`

### Φάση 3 — Ολοκλήρωση & σταθεροποίηση (Σαβ 14:00–22:00)

**Δημήτρης**
- [x] `GET /api/suggestions/{id}/explanation`: ελληνική εξήγηση από LLM, grounded στο evidence
- [x] `GET /api/customers/{trdr}/history` και `GET /api/evaluation` με πραγματικά δεδομένα
- [x] Integration tests του API (διπλό create-draft, λάθος version, εκτός ορίων, αποτυχία ERP)
- [ ] Συνέχεια στο μοντέλο (το MAE είναι 30% του βαθμού)

**Νίκος**
- [x] Σελίδες **Customer detail** και **Evaluation** — τις έκανε ο Δημήτρης (`/customers`, `/customers/[trdr]`, `/evaluation`)
- [x] Σελίδα **Overview** (Δημήτρης)
- [x] Σελίδα **Voice Operations** (Δημήτρης — διαβάζει `GET /api/calls`, κουμπί → `POST {VOICE_URL}/voice/calls`) (ουρά κλήσεων, status, transcript, draft id) + κουμπί «Κάλεσε τον πωλητή»
- [ ] Voice edge cases: voicemail, κλείσιμο γραμμής, «15» vs «50», διπλό webhook → **ποτέ** διπλό draft· allowlist, quiet hours, AI disclosure

### Φάση 4 — Τελικά (Κυρ 08:00–13:00)
**Δημήτρης**: τελικό submission (ξανατρέξιμο από καθαρό clone), `docs/RESULTS.md`, README, run-all script
**Νίκος**: polish του dashboard, 3 πρόβες της κλήσης, **ηχογράφηση fallback**, «Run demo scenario» με σταθερό seed
**Κοινό**: `docs/DEMO.md` (storyboard 2,5'), slides, πρόβα με χρονόμετρο. **13:00 code freeze.**

---

## Ιδέες αλγορίθμου (για τον Δημήτρη)

Το ground truth: «η πρώτη μέρα μετά το cutoff που το απόθεμα του πελάτη θα έφτανε στο 0 αν δεν γίνονταν άλλες παραδόσεις».
Δηλαδή το simulation έχει αόρατο απόθεμα `S(t) = S(t-1) + παραδόσεις − κατανάλωση(t)`.

1. **Καθαρή ποσότητα ανά (πελάτης, είδος, μέρα)**: τιμολόγια +, πιστωτικά −, free goods μέσα, ακυρωμένα & μεταφορικά έξω.
2. **Ρυθμός κατανάλωσης** `r`: συνολική ποσότητα / μέρες σε παράθυρο (30/60/90/180), με βάρος στα πρόσφατα. Ο πελάτης συνήθως ξαναπαραγγέλνει όταν είναι κοντά στο 0 → ο ρυθμός μεταξύ διαδοχικών αγορών ≈ ποσότητα προηγούμενης αγοράς / διάστημα.
3. **Απόθεμα στο cutoff**: `stock ≈ τελευταία παραλαβή (+υπόλοιπο) − r × (cutoff − ημ. τελευταίας αγοράς)`. Δοκίμασε και «υπόλοιπο πριν την αγορά» = μικρό safety stock που εκτιμάται από το ιστορικό.
4. **Εξάντληση**: προχωράμε μέρα-μέρα από το cutoff αφαιρώντας `r × seasonal(month, κατηγορία, τύπος/περιοχή) × promo_effect` μέχρι `stock ≤ 0`. Αν δεν πέσει πριν το 2027-01-29 → κενό.
5. **Εποχικότητα**: ο ορίζοντας είναι Νοε–Ιαν = χαμηλή σεζόν (Ιούλιος = 2,3× Ιανουάριος). Κυκλάδες/Κρήτη/ξενοδοχεία πέφτουν πολύ το χειμώνα. Υπολόγισε δείκτες από 2024–2025 (ίδιοι μήνες).
6. **Προσφορές στον ορίζοντα**: Μπύρες −10% (9–27/11), Καφές −12% (1–19/12). Μέτρα από το ιστορικό πόσο ανεβαίνει η ποσότητα στις προσφορές· στο simulation μάλλον αλλάζει ο ρυθμός αγοράς ή/και της κατανάλωσης — **έλεγξε στο backtest**.
7. **Cold start** (πελάτες με `INSDATE` 2026): shrink προς μέσο όρο peers ίδιου `TRDCATEGORY` × `AREA` × είδους.
8. **Καθαρά βελτιστοποίηση MAE**: αν η αβεβαιότητα είναι μεγάλη, η κενή τιμή κοστίζει `horizon_end − αληθινή` → για ζεύγη με μικρό ρυθμό, έλεγξε στο backtest αν συμφέρει κενό ή ημερομηνία.

Κράτα κάθε πείραμα σε μία γραμμή στο `docs/RESULTS.md`: `όνομα | backtest MAE | ±3 | ±7 | σχόλιο`.

---

## Git workflow

- `main` = πάντα τρέχει. Δουλειά σε branches `dimitris/<θέμα>` και `nikos/<θέμα>`, μικρά PR, merge γρήγορα (self-merge ok αν δεν αγγίζει contracts).
- Αλλαγή σε `docs/CONTRACTS.md` ή `fixtures/` → PR + μήνυμα στον άλλον. Οι δύο πρέπει να μένουν συγχρονισμένοι.
- **Ποτέ** secrets στο git: μόνο `.env` (gitignored). Το `.env.example` λέει τι χρειάζεται.
- Μετά από κάθε φάση: τσεκάρετε τα κουτάκια σε αυτό το αρχείο και κάνετε commit, ώστε ο άλλος (και το Claude του) να ξέρει πού είμαστε.
