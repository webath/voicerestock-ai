# apps/voice — Voice agent — Νίκος

Πλήρες brief: [`docs/VOICE.md`](../../docs/VOICE.md). Contracts: [`docs/CONTRACTS.md`](../../docs/CONTRACTS.md).

```bash
# dev χωρίς backend
python3 team_pack/mock_erp_server.py      # :8080
python3 scripts/mock_app_api.py           # :8000
ngrok http 8100                           # βάλε το URL στο .env ως VOICE_PUBLIC_URL

cd apps/voice
npm install && npm run dev                # :8100
curl -XPOST localhost:8100/voice/calls -H 'content-type: application/json' -d '{"salesman":105}'
```

Endpoints: `POST /voice/calls`, `POST /voice/twiml`, `POST /voice/status`, `WS /voice/ws`, `GET /voice/health`.
