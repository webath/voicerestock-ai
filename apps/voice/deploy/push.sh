#!/bin/bash
# push.sh — ΤΡΕΧΕΙ ΣΤΟ LAPTOP. Ανεβάζει τον κώδικα του voice agent στο VPS (/root/voicerestock).
# Δεν αλλάζει τίποτα στον agent που τρέχει· για την εναλλαγή: ssh … /root/voicerestock/deploy/deploy.sh
set -euo pipefail
VPS="${VPS:-root@159.223.11.70}"
KEY="${VPS_KEY:-$HOME/.ssh/id_ed25519_vps}"
SSH=(ssh -i "$KEY" -o IdentitiesOnly=yes -o BatchMode=yes "$VPS")
cd "$(dirname "$0")/.."   # apps/voice

python3 -m unittest discover -s tests -q 2>&1 | grep -v '^\[audit\]' | tail -2
"${SSH[@]}" 'mkdir -p /root/voicerestock/deploy'
# COPYFILE_DISABLE: χωρίς τα «._*» αρχεία του macOS
COPYFILE_DISABLE=1 tar czf - vr_core.py bot_voicerestock.py deploy/Dockerfile deploy/docker-compose.voicerestock.yml \
  deploy/deploy.sh deploy/rollback.sh deploy/voicerestock.env.example \
  | "${SSH[@]}" 'tar xzf - --no-same-owner -C /root/voicerestock && find /root/voicerestock -name "._*" -delete'
"${SSH[@]}" 'chmod +x /root/voicerestock/deploy/*.sh; ls -la /root/voicerestock /root/voicerestock/deploy'
echo "✅ Ανέβηκε. Εναλλαγή agent: ${SSH[*]} /root/voicerestock/deploy/deploy.sh"
