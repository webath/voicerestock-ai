#!/usr/bin/env bash
# Σηκώνει όλο το backend: Mock ERP :8080 → VORA agent (διαβάζει τα τιμολόγια ΑΠΟ ΤΟ ERP) → App API :8000.
#   ./scripts/dev_backend.sh          (Ctrl+C σταματά και τα δύο)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/.env" ] && set -a && . "$ROOT/.env" && set +a
export ERP_BASE_URL="${ERP_BASE_URL:-http://localhost:8080}"

echo "▶ Mock ERP :8080"
python3 "$ROOT/team_pack/mock_erp_server.py" --port 8080 &
ERP_PID=$!
trap 'kill $ERP_PID 2>/dev/null' EXIT
for _ in $(seq 1 50); do curl -sf "$ERP_BASE_URL/api/salesmen" >/dev/null && break; sleep 0.1; done

echo "▶ VORA agent: ERP → καθαρισμός → πρόβλεψη → Suggested Orders → έλεγχος → δημοσίευση"
(cd "$ROOT/services/forecast" && uv sync -q && uv run python -m forecast.agent --erp "$ERP_BASE_URL" --trigger startup)

echo "▶ App API :8000  (docs: http://localhost:8000/docs)"
cd "$ROOT/apps/api" && uv sync -q && uv run uvicorn app.main:app --port 8000
