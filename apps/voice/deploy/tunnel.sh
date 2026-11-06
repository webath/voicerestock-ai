#!/bin/bash
# tunnel.sh — ΤΡΕΧΕΙ ΣΤΟ LAPTOP και μένει ανοιχτό όσο δουλεύουμε / κατά το demo.
#
#   laptop:8100   ──▶ VPS 127.0.0.1:8100   (dashboard → κουμπί «Κάλεσε» → voice agent)
#   VPS:18000     ──▶ laptop:8000          (voice agent → App API: mock ή το πραγματικό του Δημήτρη)
#
# Τίποτα δεν ανοίγει στο internet: και τα δύο άκρα είναι localhost.
VPS="${VPS:-root@159.223.11.70}"
KEY="${VPS_KEY:-$HOME/.ssh/id_ed25519_vps}"
APP_API_PORT="${APP_API_PORT:-8000}"
echo "Tunnel προς $VPS (Ctrl+C για τέλος) — voice: http://localhost:8100/voice/health"
exec ssh -i "$KEY" -o IdentitiesOnly=yes -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -N \
  -L 8100:127.0.0.1:8100 \
  -R 127.0.0.1:18000:127.0.0.1:"$APP_API_PORT" \
  "$VPS"
