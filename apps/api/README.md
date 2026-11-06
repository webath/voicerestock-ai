# apps/api — App API (FastAPI) — Δημήτρης

Υλοποιεί **ακριβώς** τα endpoints του `docs/CONTRACTS.md` στο `:8000`.
Μέχρι να είναι έτοιμο, το `scripts/mock_app_api.py` είναι η reference υλοποίηση (ίδια συμπεριφορά: versions, tokens, idempotency).

- Διαβάζει `data/processed/suggestions.json`, `forecasts`, `evaluation` από το forecast service
- State/audit σε SQLite
- Μόνο αυτό κάνει `POST {ERP_BASE_URL}/api/draft-orders`
- CORS ανοιχτό για `:3000`

```bash
cd apps/api
uv sync && uv run uvicorn app.main:app --reload --port 8000
```
