# CLAUDE.md — οδηγίες για το Claude Code (ισχύουν και για τους δύο developers)

## Τι είναι αυτό το project

**VORA — Voice Ordering & Restock Assistant** (πρώην «VoiceRestock AI»· repo `voicerestock-ai`) — λύση για το Revival Challenge #5 (ΕΚΠΑ hackathon, 6–8/11/2026, παρουσίαση **Κυριακή 8/11 15:00**).
Από τιμολόγια ERP (SoftOne schema) προβλέπουμε πότε κάθε πελάτης θα ξεμείνει από κάθε είδος, φτιάχνουμε Suggested Orders
ως drafts στο ERP, τα δείχνουμε σε dashboard «At Risk», και ένας ελληνόφωνος voice agent καλεί τον πωλητή για να τα επιβεβαιώσει.

## Διάβασε πρώτα (με αυτή τη σειρά)

1. `docs/PLAN.md` — σειρά υλοποίησης, ποιος έχει τι, checkboxes προόδου
2. `docs/CONTRACTS.md` — σχήματα JSON & endpoints (το μόνο σημείο επαφής των δύο μερών)
3. `docs/DATA_NOTES.md` — κανόνες δεδομένων & βαθμολόγησης
4. `docs/VOICE.md` — μόνο αν δουλεύεις στο voice (Νίκος)
5. `team_pack/README_challenge.md` — η επίσημη περιγραφή (**υπερισχύει** όλων των παραπάνω)
6. `docs/challenge/*.pdf` — deck της Revival + master spec (σκεπτικό, όχι υποχρεωτικό)

## Κατάσταση & ποιος γράφει πού

Ο διαγωνισμός **τελείωσε (8/11/2026)**. Το project τρέχει τοπικά με `./scripts/start.sh`· ο voice agent στο VPS είναι κλειστός.
Η αυστηρή ιδιοκτησία φακέλων του hackathon δεν ισχύει πια: αλλάζεις ό,τι χρειάζεται, **πάντα σε branch + PR**
(`nikos/...` ή `dimitris/...`) και ποτέ κατευθείαν στο `main`. Ποιος ξέρει καλύτερα τι:

| Κομμάτι | Ποιος το έγραψε |
|---|---|
| `services/forecast/`, `apps/api/` (πυρήνας: store, agent, assistant, security, simulate), `apps/web/` (βάση), `submissions/`, `docs/RESULTS.md` | Δημήτρης |
| `apps/voice/`, `scripts/mock_app_api.py`, Campaigns / Market Scan / SMS / επαφές (`apps/api/app/{campaigns,market,outreach,contacts}.py`, σελίδες `/campaigns`, `/market`) | Νίκος |

Αλλαγή σε `docs/CONTRACTS.md` ή `fixtures/` = αλλαγή στο σημείο επαφής voice ↔ API: τρέξε `python3 scripts/check_voice_vs_api.py`.

## Αμετάβλητοι κανόνες

- **Τα δεδομένα & το README της Revival είναι η αλήθεια.** Μην επινοείς πεδία, endpoints ή νούμερα. Αν κάτι λείπει, πες το.
- Join γραμμών με headers μέσω `FINDOC`. Ακυρωμένα (`ISCANCEL=1`) έξω μαζί με τις γραμμές τους. Πιστωτικά (`SERIES=7071`) αφαιρούν ποσότητα.
  Free goods μένουν. Υπηρεσίες (`MTRTYPE=1`) έξω. Λεπτομέρειες: `docs/DATA_NOTES.md`.
- Το submission έχει **πάντα** ακριβώς τις 1.975 γραμμές του `team_pack/data/submission_template.csv`, ίδιες στήλες, ISO ημερομηνίες, κενό = καμία εξάντληση.
- **Το LLM δεν βγάζει ποτέ αριθμούς.** Ποσότητες, ημερομηνίες, confidence έρχονται από το forecast. Το LLM μόνο εξηγεί από το `evidence`.
- Μόνο το App API γράφει στο ERP (`POST /api/draft-orders`), μόνο με confirmation token, idempotent. Ποτέ τελική παραγγελία — μόνο draft.
- Κάθε βελτίωση μοντέλου μετριέται στο backtest· γράψε το αποτέλεσμα στο `docs/RESULTS.md`. Κράτα μόνο ό,τι ρίχνει το MAE.
- Ποτέ secrets στο git. Μόνο `.env` (gitignored)· νέα μεταβλητή → πρόσθεσέ τη στο `.env.example`.
- Μην αλλάζεις τίποτα μέσα στο `team_pack/` (είναι το επίσημο pack).

## Πώς τρέχει

```bash
./scripts/start.sh             # όλα: Mock ERP :8080 → agent → App API :8000 → dashboard :3000 (Ctrl+C τα κλείνει)
./scripts/dev_backend.sh       # μόνο το backend (για `npm run dev` στο apps/web)
python3 scripts/mock_app_api.py   # mock του App API πάνω σε fixture (ανάπτυξη voice χωρίς backend)
```
Τα υπόλοιπα έχουν οδηγίες στο README του φακέλου τους. Όταν προσθέτεις εντολή, ενημέρωσε το README.

## Συνήθειες

- Μικρά commits, branch `dimitris/...` ή `nikos/...`, γρήγορο merge στο `main`. Το `main` πρέπει να τρέχει πάντα.
- Όταν τελειώνει ένα κουτάκι του `docs/PLAN.md`, τσέκαρέ το (`[x]`) στο ίδιο commit — έτσι ο άλλος ξέρει πού είμαστε.
- Τρέχε τα tests του φακέλου σου πριν από κάθε push.
- Γλώσσα: κώδικας/identifiers στα αγγλικά, UI/φωνή/docs στα ελληνικά.
- Προσωπικά δεδομένα (κινητά/email πελατών) μένουν μόνο στο `data/processed/` (gitignored)· ποτέ σε fixture, test ή log.
