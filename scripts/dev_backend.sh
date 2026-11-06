#!/usr/bin/env bash
# Σηκώνει όλο το backend: forecast pipeline → Mock ERP :8080 → App API :8000.
#   ./scripts/dev_backend.sh          (Ctrl+C σταματά και τα δύο)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/.env" ] && set -a && . "$ROOT/.env" && set +a

echo "▶ forecast pipeline"
(cd "$ROOT/services/forecast" && uv sync -q && uv run python -m forecast.ingest >/dev/null \
  && uv run python -m forecast.submit && uv run python -m forecast.suggest)

echo "▶ Mock ERP :8080"
python3 "$ROOT/team_pack/mock_erp_server.py" --port 8080 &
ERP_PID=$!
trap 'kill $ERP_PID 2>/dev/null' EXIT

echo "▶ App API :8000  (docs: http://localhost:8000/docs)"
cd "$ROOT/apps/api" && uv sync -q && uv run uvicorn app.main:app --port 8000
