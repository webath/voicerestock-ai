# apps/web — Dashboard (Next.js) — Νίκος

```bash
npx create-next-app@latest . --ts --tailwind --app --eslint   # μία φορά
npm run dev                                                    # :3000, μιλάει με APP_API_URL
```

Μέχρι το checkpoint του Σαββάτου 14:00 δούλευε πάνω στο `scripts/mock_app_api.py` (ίδια endpoints με το πραγματικό API).

| Σελίδα | Path | Endpoints |
|---|---|---|
| Overview | `/` | `/api/risk`, `/api/suggestions`, `/api/calls`, `/api/evaluation` |
| At Risk (φίλτρα πωλητή, κατηγορίας, περιοχής, urgency, confidence) | `/risk` | `/api/risk`, `/api/salesmen` |
| Customer detail (timeline αγορών + forecast + factors + εξήγηση) | `/customers/[trdr]` | `/api/customers/{trdr}/history`, `/api/forecasts?trdr=`, `/api/suggestions/{id}/explanation` |
| Suggested Orders (edit qty, approve → draft id) | `/orders` | `/api/suggestions`, `.../quantity`, `.../confirm`, `.../create-draft` |
| Evaluation (baseline vs μοντέλο) | `/evaluation` | `/api/evaluation` |
| Voice Operations (κλήσεις, transcript, draft id, κουμπί «Κάλεσε») | `/voice` | `/api/calls`, `POST {VOICE_URL}/voice/calls` |

Κανόνες:
- Καμία «ψεύτικη live» τιμή: ό,τι φαίνεται έρχεται από το App API.
- Chips για εποχικότητα/προσφορά/cold start **μόνο** όταν τα δίνει το `evidence`.
- Η «Έγκριση» δείχνει επιτυχία μόνο όταν το API επιστρέψει `erp_draft_id`.
