#!/bin/bash
# deploy.sh — ΤΡΕΧΕΙ ΣΤΟ VPS. Παγώνει τον SafeVoice και σηκώνει τον VoiceRestock agent στο ίδιο container.
# Επαναφορά: /root/voicerestock/deploy/rollback.sh
#
# Τι αλλάζει: μόνο το container greek-agent (τρέχει bot_voicerestock.py από το image greek-agent:voicerestock).
# Τι ΔΕΝ αλλάζει: /root/greek-voice-agent (κώδικας, .env, git), dashboard, LiveKit trunks/rules, FreePBX.
set -euo pipefail
VR=/root/voicerestock
GV=/root/greek-voice-agent
cd "$VR"

for f in vr_core.py bot_voicerestock.py deploy/Dockerfile deploy/docker-compose.voicerestock.yml; do
  [ -s "$f" ] || { echo "❌ Λείπει το $VR/$f (τρέξε πρώτα το push.sh από το laptop)."; exit 1; }
done
grep -q "VoiceRestock σε αναμονή" bot_voicerestock.py || { echo "❌ Ελλιπές bot_voicerestock.py."; exit 1; }
[ -f voicerestock.env ] || { echo "❌ Λείπει το $VR/voicerestock.env (δες deploy/voicerestock.env.example)."; exit 1; }
COMPOSE="docker compose --project-directory $GV -f $GV/docker-compose.yml -f $VR/deploy/docker-compose.voicerestock.yml"

if [ "${1:-}" != "--force" ]; then
  echo "=== 1/5 Έλεγχος ότι δεν υπάρχει ενεργή κλήση ==="
  if ! OUT=$(docker exec greek-agent python -c "
import asyncio, sys
from livekit import api
async def m():
    async with api.LiveKitAPI() as lk:
        busy = [r for r in (await lk.room.list_rooms(api.ListRoomsRequest())).rooms if r.num_participants > 0]
        for r in busy: print('  ΠΡΟΣΟΧΗ: ενεργό δωμάτιο', r.name, r.num_participants)
        sys.exit(3 if busy else 0)
asyncio.run(m())
" 2>&1); then
    echo "$OUT" | grep -vE 'onnxruntime|pci_bus_id'
    echo "❌ Υπάρχει ενεργή κλήση (ή το LiveKit δεν απαντά). Δοκίμασε σε λίγο ή τρέξε με --force."
    exit 1
  fi
  echo "  Καμία ενεργή κλήση."
fi

echo "=== 2/5 Χτίσιμο image greek-agent:voicerestock (ο τρέχων agent συνεχίζει) ==="
docker build -q -f deploy/Dockerfile --build-arg BASE=greek-agent:safevoice -t greek-agent:voicerestock "$VR"

echo "=== 3/5 Έλεγχος ότι ο κώδικας φορτώνει ==="
docker run --rm --network host greek-agent:voicerestock \
  python -c "import bot_voicerestock as b, vr_core; assert callable(b.main); print('  import OK')" \
  2>&1 | grep -vE 'onnxruntime|pci_bus_id|Pipecat'

echo "=== 4/5 Εναλλαγή container ==="
docker inspect -f '{{.Config.Image}}' greek-agent > "$VR/PREVIOUS_IMAGE" 2>/dev/null || true
echo "  πριν: $(cat "$VR/PREVIOUS_IMAGE" 2>/dev/null || echo '-')"
docker stop greek-agent >/dev/null 2>&1 || true
docker rm greek-agent >/dev/null 2>&1 || true
$COMPOSE up -d --no-build agent

echo "=== 5/5 Αναμονή εκκίνησης ==="
set +e +o pipefail   # από εδώ και κάτω η αυτόματη επαναφορά πρέπει να τρέξει ό,τι κι αν αποτύχει
for i in $(seq 1 60); do
  if docker logs greek-agent 2>&1 | grep -q "VoiceRestock σε αναμονή"; then
    echo "✅ Ο VoiceRestock agent τρέχει."
    docker logs --tail 6 greek-agent 2>&1 | grep -vE 'onnxruntime|pci_bus_id'
    echo "   Επαναφορά SafeVoice: $VR/deploy/rollback.sh"
    exit 0
  fi
  sleep 1
done
echo "❌ Ο VoiceRestock agent δεν ξεκίνησε σε 60s. Logs:"
docker logs --tail 30 greek-agent 2>&1 | grep -vE 'onnxruntime|pci_bus_id'
echo "=== Αυτόματη επαναφορά του SafeVoice ==="
"$VR/deploy/rollback.sh" --force
exit 1
