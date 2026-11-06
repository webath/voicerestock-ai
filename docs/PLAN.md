# Πλάνο υλοποίησης & μοιρασιά δουλειάς

**Ομάδα:** Δημήτρης (data, forecast, API, dashboard) · Νίκος (Voice Agent)
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

Το voice agent είναι ανεξάρτητο κομμάτι: ο Νίκος δουλεύει από την πρώτη στιγμή πάνω σε **fixtures + mock API**
(`fixtures/suggestions.sample.json`, `scripts/mock_app_api.py`) και αλλάζει στο πραγματικό API στο checkpoint του Σαββάτου.

---

## Ποιος έχει τι (ownership)

| Περιοχή | Owner | Φάκελος |
|---|---|---|
| Ingestion, cleaning, features, forecast, backtest, submission | **Δημήτρης** | `services/forecast/` |
| App API (suggestions, quantity, confirm, create-draft, events) | **Δημήτρης** | `apps/api/` |
| Dashboard (Overview, At Risk, Customer, Suggested Orders, Evaluation) | **Δημήτρης** | `apps/web/` |
| Voice agent (Twilio, WS, STT/TTS, LLM dialogue, tools, state machine) | **Νίκος** | `apps/voice/` |
| Σελίδα «Voice Operations» στο dashboard | **Νίκος** | `apps/web/app/voice/` |
| Mock App API για ανάπτυξη voice χωρίς backend | **Νίκος** (το έχει ήδη έτοιμο) | `scripts/mock_app_api.py` |
| Contracts (σχήματα JSON, endpoints) | **κοινό** — αλλαγή μόνο με PR & ok και από τους δύο | `docs/CONTRACTS.md`, `fixtures/` |
| Pitch / demo script | κοινό | `docs/DEMO.md` |

Κανόνας: **κανείς δεν αγγίζει φάκελο του άλλου** χωρίς να του το πει. Το σημείο επαφής είναι μόνο το HTTP API του `docs/CONTRACTS.md`.
Ο voice agent **δεν** μιλάει ποτέ απευθείας με το mock ERP — μόνο με το App API.

---

## Σειρά υλοποίησης (timeline)

### Φάση 0 — Setup (Παρ 19:00–21:00)

**Κοινό (15')**: clone repo, διαβάστε `README.md`, `CLAUDE.md`, `docs/CONTRACTS.md`. Ξεκινήστε `python3 team_pack/mock_erp_server.py`.

**Δημήτρης**
- [ ] Python env (`brew install uv` → `cd services/forecast && uv sync`)
- [ ] `ingest.py`: φόρτωση SALDOC + MTRLINES, join σε FINDOC, κανόνες καθαρισμού (βλ. `docs/DATA_NOTES.md`), report με counts πριν/μετά από κάθε φίλτρο
- [ ] Tests για τους κανόνες: 0 ακυρωμένα, πιστωτικά αρνητικά, free goods μέσα, μεταφορικά έξω

**Νίκος**
- [ ] Twilio λογαριασμός + αριθμός + **verified caller ID** του κινητού του (trial κλήσεις πάνε μόνο σε verified αριθμούς) + Geo permissions για Ελλάδα
- [ ] **Spike (το πιο ρισκαρισμένο κομμάτι όλου του project):** πραγματική εξερχόμενη κλήση στο κινητό με ConversationRelay, `language=el-GR`, που απλά κάνει echo/απαντά «γεια». Επιβεβαίωση ότι STT και TTS δουλεύουν στα ελληνικά
- [ ] ngrok/cloudflared tunnel για τα webhooks
- [ ] Αν το Greek ConversationRelay δεν δουλεύει μέσα σε ~2 ώρες → Plan B (βλ. `docs/VOICE.md`)

### Φάση 1 — Πρώτο submission & βασικός voice loop (Παρ 21:00–02:00)

**Δημήτρης**
- [ ] Τοπικό **scorer** που αναπαράγει ακριβώς τον κανόνα βαθμολόγησης του README §7 (MAE, ±3, ±7, precision/recall At Risk)
- [ ] **Backtest harness**: ψεύτικο cutoff (π.χ. 2026-08-02, 2026-05-03, 2025-11-01), «αληθινή» εξάντληση από τα πραγματικά δεδομένα μετά το cutoff, scoring με τον scorer
- [ ] Baseline (μέσος ρυθμός 180 ημερών) → επιβεβαίωση ότι βγάζει ~16 μέρες MAE στο backtest
- [ ] **`submissions/team_<όνομα>.csv` v1** με 1.975 γραμμές → commit. Από εδώ και πέρα έχουμε πάντα κάτι να παραδώσουμε

**Νίκος**
- [ ] `apps/voice`: Node + TypeScript + Fastify, endpoint που επιστρέφει TwiML, WebSocket για ConversationRelay
- [ ] LLM loop με tool calling, tools υλοποιημένα πάνω στο mock App API (`scripts/mock_app_api.py`)
- [ ] Ο agent διαβάζει μια πρόταση από το fixture και την περιγράφει στα ελληνικά στο τηλέφωνο

### Φάση 2 — Καλύτερο μοντέλο & πλήρης voice ροή (Σαβ 09:00–14:00)

**Δημήτρης**
- [ ] Μοντέλο v2: ανακατασκευή αποθέματος από τον κύκλο αγορών (βλ. «Ιδέες αλγορίθμου» παρακάτω)
- [ ] Εποχικότητα (μήνας × κατηγορία είδους × τύπος/περιοχή πελάτη), αργίες, προσφορές Νοε–Δεκ, cold start από peers
- [ ] Κάθε βελτίωση: backtest → κρατάμε μόνο ό,τι ρίχνει το MAE. Πίνακας αποτελεσμάτων στο `docs/RESULTS.md`
- [ ] `suggest.py`: Suggested Order ανά πελάτη (delivery date σε εργάσιμη πριν την εξάντληση, ποσότητα, confidence, evidence) → `data/processed/suggestions.json`
- [ ] `apps/api` (FastAPI): τα endpoints του `docs/CONTRACTS.md`, διαβάζει τα παραπάνω, SQLite για state/audit

**Νίκος**
- [ ] Όλα τα tools: λίστα προτάσεων, εξήγηση, αλλαγή ποσότητας, επιβεβαίωση, create draft, status
- [ ] State machine κλήσης, διπλή προφορική επιβεβαίωση πριν από κάθε write
- [ ] Ο agent εξηγεί **μόνο** από το `evidence` (κανένας αριθμός από το LLM)

### 🔗 Checkpoint integration (Σαβ 14:00)
- Ο Δημήτρης έχει το πραγματικό API στο `:8000` με τα ίδια σχήματα με το fixture
- Ο Νίκος αλλάζει `APP_API_URL` από το mock στο πραγματικό → end-to-end: κλήση → αλλαγή ποσότητας → draft στο ERP → `team_pack/draft_orders/DRAFT-*.json`

### Φάση 3 — Dashboard & σταθεροποίηση voice (Σαβ 14:00–22:00)

**Δημήτρης**
- [ ] `apps/web` (Next.js): Overview, At Risk (φίλτρα πωλητή/κατηγορίας/περιοχής/urgency), Customer detail (timeline αγορών + forecast + factors), Suggested Orders (edit qty, approve → ERP draft id), Evaluation (baseline vs μοντέλο)
- [ ] LLM εξήγηση στο dashboard (grounded σε evidence)
- [ ] Κουμπί «Κάλεσε τον πωλητή» → `POST {VOICE_URL}/voice/calls`

**Νίκος**
- [ ] Σελίδα `apps/web/app/voice/`: ουρά κλήσεων, status, σύντομο transcript, draft id (διαβάζει `GET /api/calls`)
- [ ] Edge cases: voicemail, κλείσιμο γραμμής, «15» vs «50», διακοπές, διπλό webhook → **ποτέ** διπλό draft
- [ ] Allowlist αριθμών, quiet hours, AI disclosure στην αρχή της κλήσης

### Φάση 4 — Τελικά (Κυρ 08:00–13:00)
**Δημήτρης**: τελικό submission (ξανατρέξιμο από καθαρό clone), `docs/RESULTS.md`, README, run-all script
**Νίκος**: 3 πρόβες της κλήσης στο δωμάτιο, **ηχογράφηση fallback** (σε περίπτωση που δεν πιάνει σήμα/Twilio), demo seed
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
