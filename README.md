# VoiceRestock AI

**Predict. Explain. Call. Reorder.** — Revival Challenge #5 «The Intelligent Restocking Agent», ΕΚΠΑ hackathon 6–8/11/2026.

Από τα τιμολόγια του ERP προβλέπουμε πότε κάθε πελάτης θα ξεμείνει από κάθε είδος, δημιουργούμε Suggested Orders ως drafts στο ERP,
τα δείχνουμε σε dashboard «At Risk» και ένας ελληνόφωνος AI voice agent τηλεφωνεί στον πωλητή για να τα εξηγήσει, να αλλάξει ποσότητες
και να τα επιβεβαιώσει.

## Ομάδα

| | Ρόλος |
|---|---|
| **Δημήτρης** | Data & backend: forecasting, submission, suggested orders, App API, LLM εξηγήσεις |
| **Νίκος** | Dashboard & voice: Next.js dashboard, voice agent (Twilio + LLM) |

➡️ **Ξεκίνα από το [`docs/PLAN.md`](docs/PLAN.md)** (σειρά υλοποίησης & checkboxes) και το [`docs/CONTRACTS.md`](docs/CONTRACTS.md).

## Αρχιτεκτονική

```
team_pack/data (CSV)  ─▶  services/forecast (Python)  ─▶  forecasts + suggestions + evidence
                                                               │
Twilio ⇄ apps/voice (Node/TS) ──HTTP──▶ apps/api (FastAPI) ────┤──HTTP──▶ Mock ERP :8080 (POST /api/draft-orders)
                                              ▲
                              apps/web (Next.js dashboard)
```

| Φάκελος | Τι | Owner | Port |
|---|---|---|---|
| `team_pack/` | Επίσημο data pack + mock ERP (**μην το αλλάζετε**) | – | 8080 |
| `services/forecast/` | Ingestion, cleaning, features, model, backtest, submission, suggestions | Δημήτρης | – |
| `apps/api/` | App API: suggestions, quantity/confirm/create-draft, calls, audit | Δημήτρης | 8000 |
| `apps/web/` | Dashboard | Νίκος | 3000 |
| `apps/voice/` | Voice agent | Νίκος | 8100 |
| `scripts/mock_app_api.py` | Mock του App API πάνω σε fixture — για ανάπτυξη χωρίς backend | Νίκος | 8000 |
| `fixtures/` | Παραδείγματα JSON σύμφωνα με τα contracts | κοινό | – |
| `submissions/` | Τα CSV που υποβάλλουμε | Δημήτρης | – |
| `docs/` | Plan, contracts, data notes, voice brief, results, demo | κοινό | – |

## Quickstart

Απαιτήσεις: Python 3.11+ (`brew install uv`), Node 20+, (Νίκος) λογαριασμός Twilio + ngrok.

```bash
git clone <repo-url> && cd voicerestock-ai
cp .env.example .env                     # συμπλήρωσε ό,τι χρειάζεσαι

python3 team_pack/mock_erp_server.py     # terminal 1 — Mock ERP :8080
python3 scripts/mock_app_api.py          # terminal 2 — Mock App API :8000 (μέχρι να έρθει το apps/api)
curl "localhost:8000/api/suggestions?salesman=105"
```

Οδηγίες ανά κομμάτι: `services/forecast/README.md`, `apps/api/README.md`, `apps/web/README.md`, `apps/voice/README.md`.

## Παραδοτέα (Κυριακή 8/11)

- [ ] `submissions/team_<όνομα>.csv` — 1.975 γραμμές
- [ ] Suggested Orders JSON → `POST /api/draft-orders`
- [ ] Dashboard «At Risk» με έγκριση παραγγελίας
- [ ] Repository + live demo (με voice call)

## Για το Claude Code

Το [`CLAUDE.md`](CLAUDE.md) έχει τους κανόνες του project και ποιος γράφει σε ποιον φάκελο. Το Claude το διαβάζει αυτόματα.
