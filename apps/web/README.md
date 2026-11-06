# apps/web — Dashboard (Next.js) — Δημήτρης (+ `app/voice/` Νίκος)

```bash
npx create-next-app@latest . --ts --tailwind --app --eslint   # μία φορά
npm run dev                                                    # :3000, μιλάει με APP_API_URL
```

| Σελίδα | Path | Owner |
|---|---|---|
| Overview | `/` | Δημήτρης |
| At Risk (φίλτρα πωλητή, κατηγορίας, περιοχής, urgency) | `/risk` | Δημήτρης |
| Customer detail (timeline + forecast + factors) | `/customers/[trdr]` | Δημήτρης |
| Suggested Orders (edit qty, approve → draft id) | `/orders` | Δημήτρης |
| Evaluation (baseline vs μοντέλο) | `/evaluation` | Δημήτρης |
| Voice Operations (κλήσεις, transcript, draft id) | `/voice` | **Νίκος** |

Καμία «ψεύτικη live» τιμή: ό,τι φαίνεται έρχεται από το App API.
