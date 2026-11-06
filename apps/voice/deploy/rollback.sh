#!/bin/bash
# rollback.sh — ΤΡΕΧΕΙ ΣΤΟ VPS. Επαναφέρει τον SafeVoice (VoiceGuard) όπως έτρεχε πριν το VoiceRestock.
#   rollback.sh           κανονικά (σταματά αν υπάρχει ενεργή κλήση)
#   rollback.sh --force   χωρίς έλεγχο (π.χ. όταν ο VoiceRestock δεν ξεκίνησε καν)
# Χρησιμοποιεί το ΥΠΑΡΧΟΝ image greek-agent:safevoice και το override του ίδιου του project — δεν χτίζει τίποτα.
set -u   # ΟΧΙ -e: η επαναφορά πρέπει να φτάσει ως το τέλος
GV=/root/greek-voice-agent
cd "$GV" || exit 1

if ! docker image inspect greek-agent:safevoice >/dev/null 2>&1; then
  echo "❌ Λείπει το image greek-agent:safevoice. Χρειάζεται $GV/deploy-safevoice.sh."; exit 1
fi

if [ "${1:-}" != "--force" ] && docker ps --format '{{.Names}}' | grep -q '^greek-agent$'; then
  echo "=== Έλεγχος ενεργής κλήσης ==="
  if ! docker exec greek-agent python -c "
import asyncio, sys
from livekit import api
async def m():
    async with api.LiveKitAPI() as lk:
        busy = [r for r in (await lk.room.list_rooms(api.ListRoomsRequest())).rooms if r.num_participants > 0]
        sys.exit(3 if busy else 0)
asyncio.run(m())
" >/dev/null 2>&1; then
    echo "❌ Υπάρχει ενεργή κλήση (ή το LiveKit δεν απαντά). Ξανατρέξε σε λίγο ή με --force."; exit 1
  fi
fi

echo "=== 1/2 Εκκίνηση SafeVoice από το υπάρχον image ==="
docker stop greek-agent >/dev/null 2>&1; docker rm greek-agent >/dev/null 2>&1
docker compose -f docker-compose.yml -f docker-compose.safevoice.yml up -d --no-build agent

echo "=== 2/2 Αναμονή εκκίνησης ==="
for i in $(seq 1 60); do
  if docker logs greek-agent 2>&1 | grep -q "VoiceGuard σε αναμονή"; then
    echo "✅ Ο SafeVoice (VoiceGuard) τρέχει ξανά."
    docker logs --tail 4 greek-agent 2>&1 | grep -vE 'onnxruntime|pci_bus_id'
    exit 0
  fi
  sleep 1
done
echo "⚠️  Δεν εμφανίστηκε «VoiceGuard σε αναμονή» σε 60s:"
docker logs --tail 30 greek-agent 2>&1 | grep -vE 'onnxruntime|pci_bus_id'
exit 1
