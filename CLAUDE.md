# jarvis-tts

Text-to-speech service using Piper TTS with ONNX runtime.

## Quick Reference

```bash
# Run (Docker dev with hot reload + logging)
./run-docker-dev.sh

# Or direct (local dev)
./run-dev.sh

# Test (requires valid node auth)
curl -X POST http://localhost:7707/speak \
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
| `TTS_PORT` | 7707 | API port |
| `JARVIS_LLM_PROXY_API_URL` | - | LLM proxy for wake responses |
| `JARVIS_LLM_PROXY_API_VERSION` | 1 | LLM proxy API version |
| `JARVIS_AUTH_BASE_URL` | http://localhost:7701 | Auth service URL |
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

**Python Libraries:**
- Python 3.12, FastAPI, uvicorn, piper-tts, onnxruntime
- jarvis-log-client (for remote logging), httpx

**Service Dependencies:**
- ✅ **Required**: `jarvis-auth` (7701) - Node authentication validation
- ⚠️ **Optional**: `jarvis-llm-proxy-api` (7704) - Generate wake response greetings
- ⚠️ **Optional**: `jarvis-logs` (7702) - Centralized logging (degrades to console if unavailable)
- ⚠️ **Optional**: `jarvis-config-service` (7700) - Service discovery

**Used By:**
- `jarvis-node-setup` - Text-to-speech for voice responses

**Impact if Down:**
- ❌ No voice responses from nodes
- ❌ No wake word response greetings
- ✅ Voice input and command processing still works

## Logging

Uses jarvis-log-client for remote logging to jarvis-logs service.
Configure with `JARVIS_LOG_CONSOLE_LEVEL` and `JARVIS_LOG_REMOTE_LEVEL`.

## Docker

```bash
# Build and run
docker build -t jarvis-tts .
docker run -p 7707:7707 --env-file .env jarvis-tts
```

The Dockerfile downloads the Piper voice model during build.

## Notes

- Output is 16-bit PCM WAV
- Voice model is ~15MB (downloaded at build time)
- ONNX runtime warnings are suppressed
