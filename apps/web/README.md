# apps/web — Dashboard (Next.js 16) — Δημήτρης

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

| Σελίδα | Path | Endpoints |
|---|---|---|
| Επισκόπηση (KPIs, εξαντλήσεις/μέρα, επόμενες παραδόσεις, ανά πωλητή, κλήσεις, «Επαναφορά demo») | `/` | `/api/suggestions`, `/api/risk`, `/api/calls`, `/api/evaluation`, `/api/admin/reset` |
| At Risk (φίλτρα στο URL: `?salesman=&type=&area=&h=3\|7\|14&q=`) | `/risk` | `/api/risk`, `/api/salesmen`, `/api/suggestions` |
| Παραγγελίες (± ποσότητα, «Έγκριση & αποστολή στο ERP» → draft id, `?open=SUG-…`) | `/orders` | `/api/suggestions`, `.../quantity`, `.../confirm`, `.../create-draft`, `.../cancel` |
| Πελάτες / Πελάτης (ιστορικό, πρόβλεψη ανά είδος, πρόταση, εξήγηση) | `/customers`, `/customers/[trdr]` | `/api/customers…`, `/history`, `/api/forecasts?trdr=`, `/explanation` |
| Κλήσεις (live κάθε 3", βήματα, transcript, «Κάλεσε») | `/voice` | `/api/calls`, `POST {NEXT_PUBLIC_VOICE_URL}/voice/calls` |
| Αξιολόγηση (MAE, ±3/±7, ανά cutoff) | `/evaluation` | `/api/evaluation` |

## Θέμα «παγωμένο γυαλί»

- Γυάλινες κάρτες (`.card`: `backdrop-filter: blur(18px)`) πάνω σε φόντο με απαλές λάμψεις πάγου/aqua + κόκκο (`.backdrop`).
- Γραμματοσειρά **Commissioner** (latin + greek) μέσω `next/font`.
- Κίνηση: `.reveal` (διαδοχική εμφάνιση παιδιών), `.lift` (hover), `.grow-x/.grow-y/.grow-xb` (μπάρες), `.expand` (άνοιγμα καρτών).
  Όλα σβήνουν με `prefers-reduced-motion`.
- Light/dark από το σύστημα, ή `<html data-theme="dark|light">`.

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
