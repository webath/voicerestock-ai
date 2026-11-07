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

## Ποιος είσαι / σε ποιον φάκελο δουλεύεις

Ρώτα τον χρήστη αν δεν είναι σαφές αν είναι ο **Δημήτρης** ή ο **Νίκος**, και μείνε στους φακέλους του:

| Developer | Φάκελοι που γράφει |
|---|---|
| Δημήτρης (data, backend & dashboard) | `services/forecast/`, `apps/api/`, `apps/web/`, `submissions/`, `docs/RESULTS.md` |
| Νίκος (voice agent) | `apps/voice/`, `scripts/mock_app_api.py` (το dashboard έχει ήδη σελίδα `/voice` που διαβάζει τα events του) |
| Κοινά (μόνο με συνεννόηση) | `docs/CONTRACTS.md`, `fixtures/`, `docs/PLAN.md` (checkboxes ελεύθερα), `docs/DEMO.md`, `README.md` |

Αν μια αλλαγή χρειάζεται να αγγίξει φάκελο του άλλου ή τα contracts: **σταμάτα και πες το στον χρήστη** αντί να το κάνεις.

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
python3 team_pack/mock_erp_server.py        # Mock ERP :8080
python3 scripts/mock_app_api.py             # Mock App API :8000 (μέχρι να υπάρξει το apps/api)
```
Τα υπόλοιπα (forecast, api, web, voice) έχουν οδηγίες στο README του φακέλου τους. Όταν προσθέτεις εντολή, ενημέρωσε το README.

## Συνήθειες

- Μικρά commits, branch `dimitris/...` ή `nikos/...`, γρήγορο merge στο `main`. Το `main` πρέπει να τρέχει πάντα.
- Όταν τελειώνει ένα κουτάκι του `docs/PLAN.md`, τσέκαρέ το (`[x]`) στο ίδιο commit — έτσι ο άλλος ξέρει πού είμαστε.
- Τρέχε τα tests του φακέλου σου πριν από κάθε push.
- Γλώσσα: κώδικας/identifiers στα αγγλικά, UI/φωνή/docs στα ελληνικά.
- Προτεραιότητα όταν πιέζει ο χρόνος: submission > ERP drafts > dashboard > ακρίβεια > voice polish.
