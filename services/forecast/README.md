# services/forecast — Δημήτρης

Ingestion → cleaning → features → model → backtest → submission + suggestions.

```bash
cd services/forecast
uv sync
uv run pytest                         # 11 tests: cleaning, scoring, submission format
uv run python -m forecast.ingest      # report + data/processed/*.parquet
uv run python -m forecast.backtest    # σύγκριση μοντέλων (docs/RESULTS.md)
uv run python -m forecast.submit      # submissions/team_voicerestock.csv (default μοντέλο: hybrid_0.7)
uv run python -m forecast.suggest     # data/processed/{suggestions,forecasts,evaluation}.json για το App API
```

Τρέχον μοντέλο: **`hybrid_0.7`**, MAE backtest **3,63** (baseline 11,3). Λεπτομέρειες: `docs/RESULTS.md`.

## Modules (προτεινόμενα)

| Module | Τι κάνει | Έξοδος |
|---|---|---|
| `ingest.py` | Φόρτωση CSV από `team_pack/data`, join, cleaning (`docs/DATA_NOTES.md`), report με counts | `data/processed/daily.parquet` |
| `models.py` | Όλα τα μοντέλα + `REGISTRY` + `DEFAULT_MODEL` | – |
| `calendar.py` | Εργάσιμες, αργίες, μέρες δρομολογίου πελάτη | – |
| `score.py` | Ακριβής αναπαραγωγή βαθμολόγησης README §7 | MAE, ±3, ±7, precision/recall |
| `backtest.py` | Ψεύτικα cutoffs, αληθινή εξάντληση από τα δεδομένα, σύγκριση μοντέλων | γραμμή στο `docs/RESULTS.md` |
| `model.py` | baseline → cycle/stock → seasonal → promo → cold start | depletion date + evidence ανά ζεύγος |
| `submit.py` | 1.975 γραμμές στο format του template | `submissions/team_<όνομα>.csv` |
| `suggest.py` | Suggested Order ανά πελάτη (σχήμα `docs/CONTRACTS.md`) | `data/processed/suggestions.json` |

Το `suggestions.json` πρέπει να έχει **ακριβώς** το σχήμα του `fixtures/suggestions.sample.json`.
