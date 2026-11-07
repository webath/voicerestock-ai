# apps/api — App API (FastAPI) — Δημήτρης

Υλοποιεί τα endpoints του [`docs/CONTRACTS.md`](../../docs/CONTRACTS.md) στο `:8000`. Swagger: `http://localhost:8000/docs`.

```bash
./scripts/dev_backend.sh            # από τη ρίζα: pipeline + Mock ERP :8080 + API :8000
# ή χειροκίνητα:
cd services/forecast && uv run python -m forecast.ingest && uv run python -m forecast.suggest
cd apps/api && uv sync && uv run uvicorn app.main:app --port 8000
uv run pytest                       # 7 tests (fake ERP, χωρίς δίκτυο)
```

| Αρχείο | Τι κάνει |
|---|---|
| `app/main.py` | Endpoints, κανόνες (versions, όρια ποσότητας, confirmation token, idempotency, κλείδωμα) |
| `app/store.py` | SQLite state (`data/processed/app_state.sqlite`): suggestions, tokens, idempotency, calls, audit |
| `app/erp.py` | `MockERPAdapter` → `POST {ERP_BASE_URL}/api/draft-orders` (αντικαταστάσιμο) |
| `app/explain.py` | Ελληνική εξήγηση με Claude (`claude-opus-5-5`, effort `low`, server-side fallback). Χωρίς `ANTHROPIC_API_KEY` → template από τα ίδια πεδία |
| `app/campaigns.py` | `GET /api/campaigns`: εποχικές προσφορές (γιορτές + Ορθόδοξο Πάσχα), προτάσεις τιμών, ειδοποιήσεις «ο κύκλος έσπασε», απόδοση προσφορών — μόνο από τα τιμολόγια, χωρίς LLM |
| `app/market.py` | Market Scan: Claude + web search κάθε `MARKET_SCAN_EVERY_DAYS` (7) μέρες ή `POST /api/market/scan` → `GET /api/market`. Αποθήκευση `data/processed/market_scans.json`. Χωρίς `ANTHROPIC_API_KEY` → η σελίδα λέει τι λείπει |
| `app/outreach.py` | Αλλαγές χρήστη σε τιμές/εκπτώσεις (`PUT /api/campaigns/prices/{mtrl}`, `PUT /api/campaigns/discounts`) και SMS προσφοράς: `POST /api/campaigns/sms/draft` (κείμενο από Claude με έλεγχο αριθμών, αλλιώς πρότυπο) → `POST /api/campaigns/sms/send` (Apifon, HMAC, idempotency key). Κινητό: `SMS_DEMO_TO` ή `CUSTOMER_<TRDR>_PHONE` |

Εγγυήσεις:
- **Exactly-once draft:** το POST στο ERP γίνεται μέσα σε lock· ίδιο `idempotency_key` ή ήδη `draft_created` → ίδιο `erp_draft_id`, κανένα δεύτερο write.
- Αλλαγή ποσότητας ακυρώνει κάθε προηγούμενο `confirmation_token`.
- Αποτυχία ERP → `status: failed` (502), ξαναδοκιμάζεται με νέο idempotency key.
- Όλα τα writes στο `GET /api/audit` με `X-Actor`.
- `POST /api/admin/reset` ξαναφορτώνει τις προτάσεις από το forecast (για «Run demo scenario»).
