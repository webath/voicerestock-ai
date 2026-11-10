# services/forecast — Δημήτρης

Ingestion → cleaning → features → model → backtest → submission + suggestions.

```bash
cd services/forecast
uv sync
uv run pytest                         # cleaning, scoring, submission, accuracy, agent, χρονική απομόνωση adaptive promo
uv run python -m forecast.ingest      # report + data/processed/*.parquet
uv run python -m forecast.backtest    # σύγκριση μοντέλων, βαθμονομημένο truth + proxy (--family: ευστάθεια, -v: ανά cutoff)
uv run python -m forecast.submit      # submissions/team_voicerestock.csv (default μοντέλο: hybrid_v5)
uv run python -m forecast.suggest     # data/processed/{suggestions,forecasts,evaluation}.json για το App API
uv run python -m forecast.agent       # όλος ο κύκλος από το ERP API (ERP_BASE_URL) — ingest+submit+suggest+έλεγχοι (--source csv: από τα CSV)
```

Τρέχον μοντέλο: **`hybrid_v5`**, MAE **2,791** στα 3 αρχικά cutoffs (v3: 2,920, v4: 2,882).
Στις 6 πρόσθετες ημερομηνίες επιβεβαίωσης του v5: **2,950** έναντι v4 **3,303**.
Το truth είναι proxy σε συνθετικά δεδομένα. Το όφελος στις νέες ημερομηνίες αφορά κυρίως την άνοιξη/εποχικές επιχειρήσεις· υπάρχουν regressions.
Τα `hybrid_v3` και `hybrid_v4` παραμένουν διαθέσιμα για σύγκριση και rollback. Λεπτομέρειες: `docs/RESULTS.md`.

```bash
uv run python experiments/validate_adaptive_promo.py --output experiments/results/cadence_365.csv
uv run python experiments/validate_quantity.py --output experiments/results/quantity_v5.csv
```

Ο έλεγχος ημερομηνιών καλύπτει 23 cutoffs και 6 μοναδικούς ορισμούς truth (ένα CSV label επαναλαμβάνει το calibrated).
Τα scripts δεν γράφουν submission/runtime αρχεία. Για επαναφορά του υποβαλλόμενου αρχείου:
`uv run python -m forecast.submit --model hybrid_v4`.

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
