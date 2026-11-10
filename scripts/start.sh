#!/usr/bin/env bash
# Σηκώνει ΟΛΟ το VORA με μία εντολή: Mock ERP :8080 → agent → App API :8000 → dashboard :3000.
#   ./scripts/start.sh             build του dashboard και εκκίνηση (Ctrl+C τα σταματά όλα)
#   ./scripts/start.sh --no-build  χωρίς νέο build (πιο γρήγορο, αν δεν άλλαξε το apps/web)
# Ρυθμίσεις/κλειδιά: .env στη ρίζα (βλ. .env.example). Χωρίς κλειδιά δουλεύουν όλα εκτός από AI κείμενα, Market Scan, SMS.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$HOME/.local/bin:$PATH"
BUILD=1
[ "${1:-}" = "--no-build" ] && BUILD=0

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
die() { printf '\n❌ %s\n' "$*" >&2; exit 1; }

for tool in python3 uv node npm curl; do
  command -v "$tool" >/dev/null 2>&1 || die "Λείπει το «$tool». Δες το README (Προαπαιτούμενα)."
done
for port in 8080 8000 3000; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    die "Η θύρα $port είναι πιασμένη (τρέχει ήδη κάτι;). Κλείσε το και ξαναδοκίμασε:  lsof -nP -iTCP:$port -sTCP:LISTEN"
  fi
done
[ -f "$ROOT/.env" ] || { say "Δεν υπάρχει .env — το φτιάχνω από το .env.example (χωρίς κλειδιά)."; cp "$ROOT/.env.example" "$ROOT/.env"; chmod 600 "$ROOT/.env"; }

PIDS=()
cleanup() {
  trap - EXIT INT TERM
  say "Κλείσιμο…"
  for pid in "${PIDS[@]:-}"; do [ -n "$pid" ] && kill "$pid" 2>/dev/null || true; done
  # Οι θύρες ήταν ελεύθερες όταν ξεκινήσαμε, άρα ό,τι ακούει εκεί είναι δικό μας (uvicorn/next μένουν ορφανά αλλιώς).
  for port in 3000 8000 8080; do
    lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | while read -r p; do kill "$p" 2>/dev/null || true; done
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

say "1/3 Backend (Mock ERP → agent → App API)"
"$ROOT/scripts/dev_backend.sh" &
PIDS+=($!)
for _ in $(seq 1 180); do
  curl -sf http://localhost:8000/api/health >/dev/null 2>&1 && break
  kill -0 "${PIDS[0]}" 2>/dev/null || die "Το backend σταμάτησε — δες τα μηνύματα πιο πάνω."
  sleep 1
done
curl -sf http://localhost:8000/api/health >/dev/null 2>&1 || die "Το App API δεν απάντησε σε 3 λεπτά."

say "2/3 Dashboard"
cd "$ROOT/apps/web"
[ -d node_modules ] || npm ci
if [ "$BUILD" = 1 ] || [ ! -d .next ]; then npm run build; fi
npm start -- -p 3000 -H 127.0.0.1 &   # μόνο από αυτόν τον υπολογιστή, όχι από το τοπικό δίκτυο
PIDS+=($!)
for _ in $(seq 1 60); do curl -sf http://localhost:3000/ >/dev/null 2>&1 && break; sleep 1; done

say "3/3 Έτοιμο"
cat <<EOF
  Dashboard   http://localhost:3000
  App API     http://localhost:8000/docs
  Mock ERP    http://localhost:8080

  Live κλήσεις: θέλουν τον voice agent στο VPS + apps/voice/deploy/tunnel.sh (βλ. apps/voice/README.md).
  Χωρίς αυτά δουλεύει η «Προσομοίωση κλήσης» στη σελίδα Κλήσεις.
  Ctrl+C για να κλείσουν όλα.
EOF
wait
