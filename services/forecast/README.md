# services/forecast — Δημήτρης

Ingestion → cleaning → features → model → backtest → submission + suggestions.

```bash
cd services/forecast
uv sync
uv run pytest                         # cleaning, scoring, submission, accuracy, agent, χρονική απομόνωση adaptive promo
uv run python -m forecast.ingest      # report + data/processed/*.parquet
uv run python -m forecast.backtest    # σύγκριση μοντέλων, βαθμονομημένο truth + proxy (--family: ευστάθεια, -v: ανά cutoff)
uv run python -m forecast.submit      # submissions/team_voicerestock.csv (default μοντέλο: hybrid_v4)
uv run python -m forecast.suggest     # data/processed/{suggestions,forecasts,evaluation}.json για το App API
uv run python -m forecast.agent       # όλος ο κύκλος από το ERP API (ERP_BASE_URL) — ingest+submit+suggest+έλεγχοι (--source csv: από τα CSV)
```

Τρέχον μοντέλο: **`hybrid_v4`**, MAE backtest **2,882** έναντι v3 **2,920** στα 3 αρχικά cutoffs.
Σε 6 πρόσθετα confirmation cutoffs: **3,569** έναντι **3,622**. Το truth είναι εκτιμώμενο (proxy), όχι πραγματική απογραφή.
Το v3 παραμένει διαθέσιμο μέσω `--model hybrid_v3`. Λεπτομέρειες: `docs/RESULTS.md`.

```bash
uv run python experiments/validate_adaptive_promo.py --output experiments/results/adaptive_promo.csv
```

Η σύγκριση καλύπτει 17 cutoffs και 7 ορισμούς truth (ένας επαναλαμβάνει το calibrated για συμβατότητα με την οικογένεια).
Δεν αλλάζει submission/runtime αρχεία. Για επαναφορά του υποβαλλόμενου αρχείου: `uv run python -m forecast.submit --model hybrid_v3`.

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
