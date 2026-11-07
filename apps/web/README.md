# apps/web — Dashboard (Next.js 16) — Νίκος

Ελληνικό dashboard για τον Account Manager: ποιοι πελάτες θα ξεμείνουν, τι προτείνει το μοντέλο, έγκριση σε draft στο
ERP, και η φωνητική κλήση ζωντανά. Μιλά **μόνο** με το App API (mock ή πραγματικό, ίδια endpoints) και τον voice agent.

```bash
cd apps/web
npm install            # μία φορά
npm run dev            # http://localhost:3000
npm run build          # έλεγχος production (περνά και τα όρια του cacheComponents)
npx tsc --noEmit && npx eslint .
```

Χρειάζεται να τρέχουν:

| Τι | Πώς | Port |
|---|---|---|
| App API | `python3 scripts/mock_app_api.py` **ή** `./scripts/dev_backend.sh` (πραγματικό, Δημήτρης) | 8000 |
| Mock ERP | `python3 team_pack/mock_erp_server.py` (το `dev_backend.sh` το ανοίγει μόνο του) | 8080 |
| Voice agent (VPS) | `apps/voice/deploy/tunnel.sh` | 8100 |

Ο browser καλεί τον ίδιο origin και το Next τα προωθεί (`next.config.ts`, rewrites), οπότε δεν χρειάζεται CORS:
`/backend/*` → `APP_API_URL/api/*` (default `http://localhost:8000`), `/voice-api/*` → `VOICE_URL/voice/*` (default `http://localhost:8100`).
Αλλάζουν με `APP_API_URL=… VOICE_URL=… npm run dev`.

## Σελίδες

| Σελίδα | Path | Endpoints |
|---|---|---|
| Επισκόπηση + «Επαναφορά demo» | `/` | `/api/risk`, `/api/suggestions`, `/api/calls`, `/api/evaluation`, `POST /api/admin/reset` |
| At Risk (αναζήτηση, επείγον, κατηγορία, περιοχή, βεβαιότητα) | `/risk` | `/api/risk`, `/api/suggestions` |
| Πελάτης (γράφημα παραλαβών/εβδομάδα + πρόβλεψη + πρόταση) | `/customers/[trdr]` | `/api/customers/{trdr}/history`, `/api/forecasts?trdr=`, `/api/suggestions` |
| Προτάσεις παραγγελίας (ποσότητα, «Γιατί;», έγκριση σε 2 βήματα) | `/orders` | `/api/suggestions`, `…/quantity`, `…/confirm`, `…/create-draft`, `…/cancel`, `…/explanation` |
| Κλήσεις (κουμπί «Κάλεσε», live βήματα + transcript) | `/voice` | `/api/calls`, `POST /voice/calls`, `GET /voice/health` |
| Αξιολόγηση (MAE ανά μοντέλο, ±3/±7, P/R) | `/evaluation` | `/api/evaluation` |

Ο πωλητής επιλέγεται πάνω αριστερά και φιλτράρει όλες τις σελίδες (κρατιέται στον browser).

## Κανόνες

- Καμία «ψεύτικη live» τιμή: ό,τι φαίνεται έρχεται από το App API. Η πηγή της αξιολόγησης λέγεται πάντα (mock / τοπικό backtest).
- Chips εποχικότητας / προσφοράς / νέου πελάτη **μόνο** όταν τα δίνει το `evidence`.
- Έγκριση: πρώτα περίληψη, μετά «Ναι, δημιουργία draft» → `confirm` + `create-draft` με `idempotency_key = web:{id}:v{version}`.
  Επιτυχία φαίνεται μόνο όταν επιστρέψει `erp_draft_id`.
- Χρώματα/γραφήματα: παλέτα αναφοράς του dataviz (light/dark). Το «επείγον» έχει πάντα εικονίδιο + λέξη, όχι μόνο χρώμα.
- Next.js 16 με `cacheComponents`: κάθε `page.tsx` τυλίγει το client view σε `<Suspense>` (δες `AGENTS.md`).
