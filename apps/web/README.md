# apps/web — Dashboard (Next.js 16) — Νίκος (+ 2 σελίδες Δημήτρη)

> Next.js **16**: διάβασε το `AGENTS.md` — APIs και conventions διαφέρουν από παλιότερες εκδόσεις.
> Τα docs είναι στο `node_modules/next/dist/docs/`.

```bash
cd apps/web
npm install
npm run dev            # http://localhost:3000 — μιλάει με NEXT_PUBLIC_APP_API_URL (default http://localhost:8000)
npm run lint && npm run build
```

Χρειάζεται App API: `./scripts/dev_backend.sh` από τη ρίζα (πραγματικό) ή `python3 scripts/mock_app_api.py` (mock).

## Σελίδες

| Σελίδα | Path | Owner | Endpoints |
|---|---|---|---|
| Overview | `/` | **Νίκος** (τώρα: προσωρινό) | `/api/risk`, `/api/suggestions`, `/api/calls`, `/api/evaluation` |
| At Risk | `/risk` | **Νίκος** | `/api/risk`, `/api/salesmen` |
| Suggested Orders (edit qty, approve → draft id) | `/orders` | **Νίκος** | `/api/suggestions`, `.../quantity`, `.../confirm`, `.../create-draft` |
| Voice Operations | `/voice` | **Νίκος** | `/api/calls`, `POST {VOICE_URL}/voice/calls` |
| Πελάτες (λίστα) | `/customers` | Δημήτρης ✅ | `/api/customers`, `/api/suggestions` |
| Πελάτης (ιστορικό, πρόβλεψη ανά είδος, πρόταση, εξήγηση) | `/customers/[trdr]` | Δημήτρης ✅ | `/api/customers/{trdr}`, `/history`, `/api/forecasts?trdr=`, `/explanation` |
| Αξιολόγηση (MAE, ±3/±7, ανά cutoff) | `/evaluation` | Δημήτρης ✅ | `/api/evaluation` |

Η At Risk / Orders μπορούν να κάνουν link σε `/customers/{TRDR}` για λεπτομέρειες.

## Κοινά κομμάτια (χρησιμοποίησέ τα)

| Αρχείο | Τι έχει |
|---|---|
| `lib/api.ts` | Types όλων των σχημάτων του `docs/CONTRACTS.md` + `apiGet()` + hook `useApi(path)` |
| `lib/format.ts` | Ελληνική μορφοποίηση (`fmtDay`, `fmtPct`, …), ονόματα μοντέλων/factors |
| `components/ui.tsx` | `PageHeader`, `Card`, `StatTile`, `UrgencyBadge` (εικονίδιο + κείμενο), `Chip`, `ErrorBox`, `Loading` |
| `components/charts/` | `MaeBarChart`, `PurchaseTimeline` (SVG, χωρίς βιβλιοθήκη, με tooltip) |
| `app/globals.css` | Tokens χρωμάτων light/dark (`--surface`, `--ink`, `--series-1`, status…) — γράφε με ρόλους, όχι hex |

Κανόνες:
- Καμία «ψεύτικη live» τιμή: ό,τι φαίνεται έρχεται από το App API.
- Chips για εποχικότητα/προσφορά/cold start **μόνο** όταν τα δίνει το `evidence`.
- Status (επείγον κ.λπ.) πάντα με εικονίδιο + κείμενο, ποτέ μόνο χρώμα.
- Η «Έγκριση» δείχνει επιτυχία μόνο όταν το API επιστρέψει `erp_draft_id`.
