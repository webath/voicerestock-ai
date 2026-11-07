#!/bin/bash
# tunnel.sh — ΤΡΕΧΕΙ ΣΤΟ LAPTOP και μένει ανοιχτό όσο δουλεύουμε / κατά το demo.
#
#   laptop:8100   ──▶ VPS 127.0.0.1:8100   (dashboard → κουμπί «Κάλεσε» → voice agent)
#   VPS:18000     ──▶ laptop:8000          (voice agent → App API: mock ή το πραγματικό του Δημήτρη)
#
# Τίποτα δεν ανοίγει στο internet: και τα δύο άκρα είναι localhost.
# Αν πέσει η σύνδεση (Wi-Fi, «Broken pipe», timeout), ξανασυνδέεται μόνο του σε 3″. Ctrl+C για τέλος.
VPS="${VPS:-root@159.223.11.70}"
KEY="${VPS_KEY:-$HOME/.ssh/id_ed25519_vps}"
APP_API_PORT="${APP_API_PORT:-8000}"

trap 'echo; echo "Tunnel: τέλος."; exit 0' INT TERM
echo "Tunnel προς $VPS — voice: http://localhost:8100/voice/health · App API για το VPS: laptop:$APP_API_PORT"
while true; do
  ssh -i "$KEY" -o IdentitiesOnly=yes -o BatchMode=yes -o ExitOnForwardFailure=yes \
    -o ConnectTimeout=10 -o ServerAliveInterval=10 -o ServerAliveCountMax=3 -N \
    -L 8100:127.0.0.1:8100 \
    -R 127.0.0.1:18000:127.0.0.1:"$APP_API_PORT" \
    "$VPS"
  rc=$?
  echo "$(date '+%H:%M:%S') Tunnel: η σύνδεση έπεσε (κωδικός $rc) — ξανασύνδεση σε 3″…"
  sleep 3
done
