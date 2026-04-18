# jarvis-tts

Multi-provider text-to-speech service. Piper (ONNX, baked into image) is the always-available fallback; Kokoro (82M-param HF model, downloaded on first use) is the optional natural-prosody provider. Providers are selected at runtime via the `tts.provider` setting.

## Quick Reference

```bash
# Run (Docker dev with hot reload + logging)
./run-docker-dev.sh

# Or direct (local dev)
./run-dev.sh

# Test (requires valid app-to-app auth headers)
curl -X POST http://localhost:7707/speak \
  -H "X-Jarvis-App-Id: <app_id>" \
  -H "X-Jarvis-App-Key: <app_key>" \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world"}'
```

## Architecture

```
app/
├── main.py                         # FastAPI routes
├── deps.py                         # App-to-app auth
├── providers/
│   ├── base.py                     # TTSProvider ABC, AudioFormat, AudioChunk
│   ├── piper_provider.py           # Piper backend (always available)
│   ├── kokoro_provider.py          # Kokoro backend (optional extra)
│   └── registry.py                 # Registration + Piper-fallback loader
├── services/
│   ├── provider_manager.py         # Lazy reload on settings change
│   ├── settings_service.py         # DB-backed settings with 60s cache
│   └── settings_definitions.py     # Setting schema
└── models/                         # Piper ONNX + HF cache dir
```

- **Default provider**: Piper (`en_GB-alan-low`, 22050 Hz, baked in)
- **Optional provider**: Kokoro (default voice `bm_george`, 24000 Hz, weights in `HF_HOME`)
- **Switching**: update `tts.provider` via settings API — takes effect within ~60s (settings cache TTL). Failed reload falls back to Piper with a warning log.

## Settings

| Key | Default | Description |
|-----|---------|-------------|
| `tts.provider` | `kokoro` | Active provider: `piper` or `kokoro` |
| `tts.default_voice` | `en_GB-alan-low` | Piper ONNX voice file stem in `app/models/` |
| `tts.kokoro_voice` | `bm_george` | Kokoro voice ID (e.g., `bm_george`, `bm_fable`) |
| `tts.kokoro_speed` | `1.25` | Kokoro speed multiplier |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TTS_PORT` | 7707 | API port |
| `TTS_PROVIDER` | `kokoro` | Initial provider (overridden by DB setting once present) |
| `TTS_DEFAULT_VOICE` | `en_GB-alan-low` | Piper voice (env fallback for setting) |
| `TTS_KOKORO_VOICE` | `bm_george` | Kokoro voice (env fallback for setting) |
| `TTS_KOKORO_SPEED` | `1.25` | Kokoro speed (env fallback for setting) |
| `HF_HOME` | `/app/models/hf_cache` | Kokoro weight cache (mount as named volume) |
| `JARVIS_LLM_PROXY_API_URL` | - | LLM proxy for wake responses |
| `JARVIS_AUTH_BASE_URL` | http://localhost:7701 | Auth service URL |
| `JARVIS_APP_ID` | jarvis-tts | App ID for app-to-app auth |
| `JARVIS_APP_KEY` | - | App key (required) |
| `NODE_AUTH_CACHE_TTL` | 60 | Auth validation cache TTL |

## API Endpoints

- `GET /ping` → `{"message": "pong"}` (no auth)
- `GET /health` → `{"status": "healthy"}` (no auth)
- `GET /audio/format` → provider's sample rate / width / channels + provider name
- `POST /speak` → `audio/wav` (full buffer)
- `POST /speak/stream` → raw 16-bit PCM with `X-Audio-*` headers (low-latency)
- `POST /generate-wake-response` → `{"text": "..."}` via LLM proxy

## Dependencies

**Python Libraries:**
- Python 3.11+, FastAPI, uvicorn, piper-tts, onnxruntime
- `kokoro`, `soundfile`, `numpy` (via `.[kokoro]` extra, optional)
- jarvis-log-client, httpx

**Service Dependencies:**
- ✅ **Required**: `jarvis-auth` (7701) — app auth validation
- ⚠️ **Optional**: `jarvis-llm-proxy-api` (7704) — wake-response generation
- ⚠️ **Optional**: `jarvis-logs` (7702) — centralized logging (degrades to console)
- ⚠️ **Optional**: `jarvis-config-service` (7700) — service discovery

**Used By:**
- `jarvis-node-setup` — `/speak/stream` for voice responses

**Impact if Down:**
- ❌ No voice responses; wake greetings disabled
- ✅ Voice input, command processing, and everything else continues

## Docker

```bash
# Build with Kokoro extra (default)
docker build -t jarvis-tts .

# Build without Kokoro (image-only fallback)
docker build --build-arg INSTALL_EXTRAS="" -t jarvis-tts .

# Run with persistent Kokoro cache
docker run -p 7707:7707 \
  -v jarvis-tts-hf-cache:/app/models/hf_cache \
  --env-file .env jarvis-tts
```

The Piper voice model (~15 MB) is baked in. Kokoro weights (~300 MB) download on first use to `HF_HOME` — mount the `jarvis-tts-hf-cache` volume so restarts don't re-download.

## Logging

Uses jarvis-log-client for remote logging to jarvis-logs service.
Configure with `JARVIS_LOG_CONSOLE_LEVEL` and `JARVIS_LOG_REMOTE_LEVEL`.

## Testing

```bash
.venv/bin/pytest
```

76 tests covering endpoints, provider registry, Piper wrapper, provider manager fingerprint reload, and settings.

## Notes

- Output: 16-bit PCM (WAV via `/speak`, raw via `/speak/stream`)
- Sample rate varies by provider (Piper 22050 Hz, Kokoro 24000 Hz). Clients read `X-Audio-Sample-Rate` response header and hand it to `aplay` — no resampling needed.
- ONNX runtime warnings are suppressed
