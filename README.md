# VORA — Voice Ordering & Restock Assistant

**Predict. Explain. Call. Reorder.** — Revival Challenge #5 «The Intelligent Restocking Agent», ΕΚΠΑ hackathon 6–8/11/2026.

Από τα τιμολόγια του ERP προβλέπουμε πότε κάθε πελάτης θα ξεμείνει από κάθε είδος, φτιάχνουμε Suggested Orders ως drafts στο ERP,
τα δείχνουμε σε dashboard «At Risk», και ένας ελληνόφωνος AI voice agent τηλεφωνεί στον πωλητή για να τα εξηγήσει, να αλλάξει
ποσότητες και να τα επιβεβαιώσει. Πάνω σε αυτά: προτάσεις προσφορών/τιμών (Campaigns), εβδομαδιαία έρευνα αγοράς (Market Scan)
και SMS προσφοράς στον πελάτη.

> **Κατάσταση (11/2026):** ο διαγωνισμός τελείωσε. Το project τρέχει **τοπικά, σε έναν υπολογιστή**, με μία εντολή.
> Ο voice agent στο VPS είναι κλειστός (το VPS τρέχει ξανά το προηγούμενο project)· στο dashboard δουλεύει η «Προσομοίωση κλήσης».

📖 Πώς δουλεύει όλο το σύστημα, βήμα βήμα: [`docs/HOW_IT_WORKS.md`](docs/HOW_IT_WORKS.md) · Ασφάλεια: [`docs/SECURITY.md`](docs/SECURITY.md)

## Εκκίνηση με μία εντολή

Προαπαιτούμενα: Python 3.9+, [`uv`](https://docs.astral.sh/uv/) (φέρνει μόνο του την Python που θέλουν τα services), Node 20+.

```bash
git clone <repo-url> && cd voicerestock-ai
./scripts/start.sh            # Mock ERP :8080 → agent (πρόβλεψη) → App API :8000 → dashboard http://localhost:3000
```

- Το Ctrl+C τα κλείνει όλα. `./scripts/start.sh --no-build` ξεκινά πιο γρήγορα όταν δεν άλλαξε το `apps/web`.
- Αν δεν υπάρχει `.env`, το φτιάχνει από το `.env.example`. Όλα ακούνε **μόνο στο 127.0.0.1**.
- Ανάπτυξη σε δύο terminal: `./scripts/dev_backend.sh` και `cd apps/web && npm install && npm run dev`.

### Τι δουλεύει χωρίς κλειδιά και τι θέλει κλειδί (`.env`)

| Λειτουργία | Χωρίς κλειδιά | Με κλειδί |
|---|---|---|
| Πρόβλεψη, At Risk, Παραγγελίες → draft στο ERP, Campaigns, Αξιολόγηση, Προσομοίωση κλήσης | ✅ | – |
| Εξηγήσεις, πρωινό briefing, AI βοηθός, κείμενο SMS | σταθερό πρότυπο | `ANTHROPIC_API_KEY` |
| Market Scan (έρευνα αγοράς με web search, ~8 αναζητήσεις ανά έρευνα) | ❌ | `ANTHROPIC_API_KEY` |
| Αποστολή SMS | μόνο προεπισκόπηση | `APIFON_TOKEN`, `APIFON_SECRET`, `APIFON_SENDER` |
| Live τηλεφωνική κλήση | ❌ | voice agent στο VPS + `apps/voice/deploy/tunnel.sh` ([`apps/voice/README.md`](apps/voice/README.md)) |

**SMS — demo ή πραγματικά.** Το ERP δεν δίνει κινητά πελατών. Στη σελίδα **Πελάτες** ανεβάζεις CSV με κινητά/email (ή τα βάζεις
ένα-ένα) και διαλέγεις: **Demo** = όλα τα SMS πάνε στο `SMS_DEMO_TO`, **Πραγματικά** = στο κινητό του ίδιου του πελάτη (ζητά
επιβεβαίωση· πελάτης χωρίς κινητό δεν παίρνει SMS). Οι επαφές μένουν στο `data/processed/customer_contacts.json`, εκτός git.

## Αρχιτεκτονική

```
Mock ERP :8080 ──τιμολόγια──▶ services/forecast (agent: καθαρισμός → πρόβλεψη → Suggested Orders → αυτοέλεγχος)
      ▲                                   │ data/processed/*.json
      │ POST /api/draft-orders            ▼
apps/api (FastAPI :8000) ◀──HTTP── apps/web (Next.js dashboard :3000)
      ▲            └──▶ Anthropic API (εξηγήσεις, Market Scan) · Apifon (SMS)
      │ SSH tunnel (μόνο για live κλήσεις)
apps/voice στο VPS: Pipecat + LiveKit SIP → FreePBX → τηλεφωνικό δίκτυο
```

| Φάκελος | Τι | Port |
|---|---|---|
| `team_pack/` | Επίσημο data pack + mock ERP (**δεν αλλάζει**) | 8080 |
| `services/forecast/` | Ingestion, καθαρισμός, μοντέλο (hybrid_v5), backtest, submission, agent | – |
| `apps/api/` | App API: προτάσεις, έγκριση → draft, κλήσεις, audit, Campaigns, Market Scan, SMS, επαφές | 8000 |
| `apps/web/` | Dashboard: Επισκόπηση, Agent, At Risk, Παραγγελίες, Πελάτες, Κλήσεις, Campaigns, Market Scan, Αξιολόγηση | 3000 |
| `apps/voice/` | Voice agent (τρέχει στο VPS· `deploy/` για εναλλαγή και rollback) | 8100 |
| `scripts/` | `start.sh` (όλα), `dev_backend.sh` (backend), `mock_erp_local.py` (ERP μόνο στο 127.0.0.1), `check_voice_vs_api.py`, `mock_app_api.py` | – |
| `fixtures/`, `docs/`, `submissions/` | Παραδείγματα JSON των contracts · τεκμηρίωση · το CSV του διαγωνισμού | – |

## Έλεγχοι

```bash
(cd apps/api && uv run pytest)                       # App API
(cd services/forecast && uv run pytest)              # μοντέλο & agent
python3 -m unittest discover -s apps/voice/tests     # λογική voice agent
(cd apps/web && npx tsc --noEmit && npm run lint)    # dashboard
python3 scripts/check_voice_vs_api.py                # voice πάνω στο πραγματικό API: «ΟΛΑ ΟΚ»
```

## Ομάδα

**Δημήτρης** — δεδομένα, μοντέλο πρόβλεψης, App API, dashboard. **Νίκος** — voice agent, Campaigns, Market Scan, SMS.

Το [`CLAUDE.md`](CLAUDE.md) έχει τους κανόνες του project για το Claude Code.
