# apps/api — App API (FastAPI) — Δημήτρης

Υλοποιεί **ακριβώς** τα endpoints του `docs/CONTRACTS.md` στο `:8000`.
Το `scripts/mock_app_api.py` είναι η reference συμπεριφορά (versions, tokens, idempotency): το dashboard και το voice
του Νίκου είναι χτισμένα πάνω του, άρα το πραγματικό API πρέπει να απαντά με τα ίδια σχήματα.

- Διαβάζει `data/processed/suggestions.json`, forecasts, evaluation από το forecast service
- State/audit σε SQLite
- Μόνο αυτό κάνει `POST {ERP_BASE_URL}/api/draft-orders`
- `/explanation`: LLM (Claude) που παίρνει **μόνο** το evidence και βγάζει ελληνικό κείμενο, χωρίς νέους αριθμούς
- CORS ανοιχτό για `:3000`

```bash
cd apps/api
uv sync && uv run uvicorn app.main:app --reload --port 8000
```
