# jarvis-tts

Text-to-speech service using Piper TTS with ONNX runtime.

## Quick Reference

```bash
# Run (Docker)
docker-compose up -d

# Or direct
pip install -r requirements.txt
uvicorn app.main:app --port 8009

# Test (requires valid node auth)
curl -X POST http://localhost:8009/speak \
  -H "X-API-Key: node_id:node_key" \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world"}'
```

## Architecture

```
app/
├── main.py      # FastAPI routes: /ping, /speak, /generate-wake-response
├── deps.py      # Node authentication via jarvis-auth
└── models/      # Piper ONNX voice models
```

- **TTS Engine**: Piper TTS with ONNX runtime
- **Voice**: en_GB-alan-low (British English)
- **Authentication**: Nodes authenticate via jarvis-auth service

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TTS_PORT` | 8009 | API port |
| `JARVIS_LLM_PROXY_API_URL` | - | LLM proxy for wake responses |
| `JARVIS_LLM_PROXY_API_VERSION` | 1 | LLM proxy API version |
| `JARVIS_AUTH_BASE_URL` | http://localhost:8007 | Auth service URL |
| `JARVIS_APP_ID` | jarvis-tts | App ID for auth |
| `JARVIS_APP_KEY` | - | App key (required for auth) |
| `NODE_AUTH_CACHE_TTL` | 60 | Cache TTL for auth validation |

## API Endpoints

- `GET /ping` → `{"message": "pong"}` (no auth required)
- `POST /speak` → WAV audio (auth required)
  - Header: `X-API-Key: node_id:node_key`
  - Body: `{"text": "Text to speak"}`
  - Returns: `audio/wav`
- `POST /generate-wake-response` → `{"text": "..."}` (auth required)
  - Generates a random wake greeting via LLM

## Dependencies

- **Runtime**: Python 3.12, FastAPI, uvicorn, piper-tts, onnxruntime
- **Jarvis**: jarvis-log-client (for remote logging), httpx

## Logging

Uses jarvis-log-client for remote logging to jarvis-logs service.
Configure with `JARVIS_LOG_CONSOLE_LEVEL` and `JARVIS_LOG_REMOTE_LEVEL`.

## Docker

```bash
# Build and run
docker build -t jarvis-tts .
docker run -p 8009:8009 --env-file .env jarvis-tts
```

The Dockerfile downloads the Piper voice model during build.

## Notes

- Output is 16-bit PCM WAV
- Voice model is ~15MB (downloaded at build time)
- ONNX runtime warnings are suppressed
