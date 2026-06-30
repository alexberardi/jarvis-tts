# jarvis-tts

Text-to-speech with **two interchangeable providers** (Piper as the always-available baked-in fallback, Kokoro as the higher-quality optional upgrade). Provider selection is settings-driven with hot-swap via a fingerprint-reload pattern. Outputs streamed raw PCM (low latency) or buffered WAV.

> **Identity rule:** TTS is a pure synthesizer. It doesn't *decide* what to say — that's command-center's job. The legacy `/generate-wake-response` endpoint is a deprecated shim and should not be extended.

---

## Providers

| Provider | Default voice | Sample rate | Size | When to use |
|---|---|---|---|---|
| **Piper** (ONNX) | `en_GB-alan-low` | 22050 Hz | ~15 MB (baked into image) | **Default in current settings.** Always available, zero runtime egress. Fast, robotic, reliable. Fallback when Kokoro fails. |
| **Kokoro** (PyTorch / HF) | `bm_george` | 24000 Hz | ~300 MB (downloaded on first use to `HF_HOME`) | Natural prosody. **Explicit opt-in** (set `tts.provider=kokoro`). Quieter output — `tts.kokoro_gain` compensates (default 2.0 ≈ +6 dB). |

**Switch live:** update `tts.provider` via the settings API. Within ~60s (settings cache TTL) the provider manager notices the fingerprint change, swaps the active provider, and any in-flight requests using the old provider continue to completion. **Failed reload falls back to Piper with a warning log** — the service never goes silent.

The sample rate **changes when you switch providers**. Clients must read `X-Audio-Sample-Rate` from the response headers each request — don't cache it across provider switches.

---

## Quick Reference

```bash
# Dev (Docker)
./run-docker-dev.sh

# Bare metal
./run.sh

# Smoke test
curl -X POST http://localhost:7707/speak \
  -H "X-Jarvis-App-Id: $APP_ID" -H "X-Jarvis-App-Key: $APP_KEY" \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world"}' --output hello.wav

# Test
.venv/bin/pytest    # 76 tests; no model needed (Piper mocked)
```

---

## Dependency graph

**Upstream (TTS depends on):**
- **Piper ONNX model** (baked into image) — required, fallback path
- **Kokoro weights** (downloaded to `HF_HOME` on first use) — required only if `tts.provider=kokoro`
- **jarvis-auth** (port 7701) — app-to-app validation per request (cached)
- **jarvis-config-service** (port 7700) — service discovery
- **jarvis-logs** (port 7702, optional) — remote logging
- **PostgreSQL** (required) — own settings table
- **jarvis-llm-proxy-api** (port 7704, optional) — used **only** by the deprecated `/generate-wake-response` shim

**Downstream (depends on TTS):**
- **jarvis-command-center** — pipes streaming voice responses through TTS for the voice/Pi path (`/speak/stream`)
- **jarvis-node-setup** — historically called `/generate-wake-response` directly; new nodes call CC `/api/v0/wake-response` instead

**Impact if down:**
- Voice responses disappear. Input + processing continue; the user hears nothing.

---

## How it actually runs

### Startup
1. `service_config.init()` — discover other services
2. `_setup_remote_logging()` — best-effort jarvis-logs hookup
3. `get_active_provider()` — **pre-warm** the active provider (per `tts.provider` setting; **default `piper`**, which loads from disk in ~100ms with zero runtime egress). When opted in to Kokoro, it pulls weights from HF if not cached, then loads to device (`cpu` / `cuda` / `mps`) per `tts.kokoro_device`. **Failure is non-fatal** — provider manager falls back to Piper on first real request.

### Per request
1. **Auth** — `verify_app_auth` validates `X-Jarvis-App-Id` + `X-Jarvis-App-Key` via auth, surfaces `X-Context-*` headers (household, node).
2. **Provider resolution** — `get_active_provider()` checks the settings fingerprint. If `tts.provider`, `tts.default_voice`, `tts.kokoro_voice`, `tts.kokoro_speed`, `tts.kokoro_device`, or `tts.kokoro_gain` changed, rebuild before returning.
3. **Synthesis** — provider yields `AudioChunk` objects (16-bit PCM frames).
4. **Output**:
   - `/speak` — wraps the full byte buffer in a WAV container and returns `audio/wav` (single response).
   - `/speak/stream` — streams raw PCM bytes with audio format in headers (`X-Audio-Sample-Rate`, `X-Audio-Channels`, `X-Audio-Sample-Width`, `X-Audio-Provider`). The caller hands these straight to `aplay` (no resampling).

---

## "How to..." recipes

### Add a new TTS provider

1. Subclass `app/providers/base.py:TTSProvider`. Implement `synthesize()` (yield `AudioChunk`s), `get_audio_format()`, and `name`.
2. Register in `app/providers/registry.py` — add to the registry dict and ensure the import is gated for optional deps.
3. Add settings to `app/services/settings_definitions.py` for any provider-specific knobs (voice, speed, device, gain).
4. Add the provider name to the `options` list on `tts.provider`.
5. Tests under `tests/test_<provider>_provider.py` — mock the underlying lib, not the wrapper.

### Add a new voice for an existing provider

For Piper: drop the ONNX file in `app/models/<voice_name>.onnx`, set `tts.default_voice=<voice_name>`. **No code change needed.**

For Kokoro: voices ship inside the HF model. Set `tts.kokoro_voice=<voice_id>`. Available voice IDs are documented in the Kokoro upstream; common ones: `bm_george`, `bm_fable`, `af_heart`.

### Tune Kokoro loudness

`tts.kokoro_gain` (default 2.0). Each step doubles amplitude:
- `1.0` — raw output (peaks 0.3-0.5, perceptually quiet)
- `2.0` — +6 dB (peaks ~0.7, safe — default)
- `3.0` — +9.5 dB (peaks near full scale, mild saturation on loud chunks)

Don't go above 3.0 — clipping artifacts become audible.

### Add a TTS setting

Same pattern as the rest of the stack:
1. `SettingDefinition` in `app/services/settings_definitions.py` with `env_fallback` for migration
2. If it should trigger a provider reload, add the key to the fingerprint set in `app/services/provider_manager.py`

---

## Invariants & gotchas

1. **`/generate-wake-response` is DEPRECATED.** It's a shim for pre-v0.1.14 nodes. New code should call **`jarvis-command-center POST /api/v0/wake-response`** instead — CC owns the prompt provider and can do provider-aware sanitation (e.g., strip think-blocks). Don't add features here. Don't add the wake_system_prompt to the prompt anywhere except CC.
2. **Settings cache TTL is ~60s** (default in jarvis-settings-client). Provider swaps via `PUT /settings/tts.provider` take effect within this window. Don't expect immediate effect after a write; either wait or restart.
3. **Failed provider reload falls back to Piper.** A bad `tts.kokoro_voice` or missing Kokoro weights will degrade — not crash. Check warning logs (`logger.warning "Failed to ..."`) to detect silent degradation.
4. **`/speak` returns WAV; `/speak/stream` returns raw PCM.** The header difference matters — the streaming path skips WAV encoding for first-chunk latency. Callers must read `X-Audio-Sample-Rate` headers and pass them to playback.
5. **Sample rates differ between providers** (Piper 22050 / Kokoro 24000). The audio format response header is the source of truth; never hard-code rates in callers.
6. **Kokoro weights are NOT in the image — they're downloaded on first request.** Mount `jarvis-tts-hf-cache:/app/models/hf_cache` as a Docker volume so restarts don't re-download. First request after a fresh install can take 30s+; subsequent are instant.
7. **`INSTALL_EXTRAS` build arg controls Kokoro inclusion.** Default builds include Kokoro. `--build-arg INSTALL_EXTRAS=""` builds a smaller image with Piper-only. If you need a stripped-down deployment (low-RAM nodes acting as TTS servers), use this.
8. **ONNX runtime warnings are suppressed** (`ort.set_default_logger_severity(3)` at module top). Don't relax this without good reason — it floods the logs.
9. **No streaming wake-word generation.** The wake-response endpoint returns the full text in one response. If you want streaming, do it at the CC layer (`/api/v0/wake-response` can stream — verify before assuming).
10. **`X-Context-*` headers carry household/node identity.** Command-center sets them when proxying. Don't try to do household auth here — the upstream did it.

---

## API surface

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/ping` | none | |
| GET | `/health` | none | Shallow — doesn't check provider |
| GET | `/audio/format` | app-auth | Active provider's sample rate, channels, width, name |
| POST | `/speak` | app-auth | Body `{text}`; returns `audio/wav` |
| POST | `/speak/stream` | app-auth | Body `{text}`; returns raw PCM + `X-Audio-*` headers |
| POST | `/generate-wake-response` | app-auth | **DEPRECATED** — shim. Calls llm-proxy and returns `{text}` |
| `/settings/*` | combined / superuser | Library mount |

---

## Data model

**No tables of its own** beyond `multitenant_settings`. Voice files live on disk:
- Piper: `app/models/<voice>.onnx` (baked into image)
- Kokoro: `$HF_HOME/...` (downloaded; mount as volume)

---

## Config surface

**Env vars (bootstrap + secrets only):**

| Variable | Required | Purpose |
|---|---|---|
| `JARVIS_CONFIG_URL` | yes | Service discovery |
| `JARVIS_APP_ID` / `JARVIS_APP_KEY` | yes | App credential for logging + auth |
| `DATABASE_URL` | yes | Postgres |
| `HF_HOME` | yes (Kokoro) | Kokoro weights cache directory. Default `/app/models/hf_cache`. Mount as volume. |
| `JARVIS_LLM_PROXY_API_URL` | optional | Fallback for deprecated `/generate-wake-response` |
| `JARVIS_LOG_CONSOLE_LEVEL` / `JARVIS_LOG_REMOTE_LEVEL` | optional | Logging |
| `TTS_PORT` | optional (7707) | API bind |

**DB-backed settings (canonical):**

| Key | Default | Notes |
|---|---|---|
| `tts.provider` | `piper` | `piper` \| `kokoro` (kokoro is explicit opt-in — downloads HF weights on first use) |
| `tts.default_voice` | `en_GB-alan-low` | Piper voice (stem under `app/models/`) |
| `tts.kokoro_voice` | `bm_george` | Kokoro voice ID |
| `tts.kokoro_speed` | `1.25` | Multiplier; >1 = faster |
| `tts.kokoro_device` | `cpu` | `cpu` \| `cuda` \| `mps` |
| `tts.kokoro_gain` | `2.0` | +6 dB by default; see gotcha #4 |
| `tts.wake_system_prompt` | (canned) | Used by deprecated wake-response — leave alone |
| `tts.llm_proxy_version` | 1 | Deprecated wake-response API version |

All settings reload via the manager fingerprint on next request (~60s cache TTL).

---

## Architecture

```
jarvis-tts/
├── app/
│   ├── main.py                              # FastAPI: /ping /health /audio/format /speak /speak/stream /generate-wake-response
│   ├── deps.py                              # verify_app_auth = require_app_auth()
│   ├── service_config.py                    # jarvis-config-client wrapper
│   ├── providers/
│   │   ├── base.py                          # TTSProvider ABC, AudioFormat, AudioChunk
│   │   ├── piper_provider.py                # ONNX baked-in
│   │   ├── kokoro_provider.py               # PyTorch / HF, optional
│   │   └── registry.py                      # Provider registration + Piper-fallback loader
│   ├── services/
│   │   ├── provider_manager.py              # Lazy load + fingerprint reload
│   │   ├── settings_definitions.py          # SettingDefinitions
│   │   └── settings_service.py
│   ├── db/                                  # SQLAlchemy session
│   └── models/                              # Piper ONNX voices + Kokoro HF cache dir
├── alembic/                                 # Settings migrations
├── tests/                                   # 76 tests, no real model needed
├── setup-piper.sh                           # Build Piper ONNX runtime
├── Dockerfile                               # INSTALL_EXTRAS=kokoro by default
└── docker-compose.{dev,prod}.yaml
```

---

## Testing

```bash
.venv/bin/pytest
```

76 tests covering: endpoints, provider registry, Piper wrapper, provider manager fingerprint reload, settings service. **No real model is loaded** — Piper is mocked, Kokoro is mocked. Tests run anywhere.

---

## Failure modes

| Failure | Behavior |
|---|---|
| Auth down | All endpoints 401/503 |
| Postgres down | Settings reads use env-var fallback; provider switching disabled |
| Active provider fails to load | Falls back to Piper with warning log |
| Kokoro weights unreachable | Falls back to Piper |
| Settings DB returns garbage value | Provider manager logs the error and keeps current provider |
| `tts.kokoro_gain > ~3.0` | Audible clipping on loud chunks |
| HF_HOME volume not mounted | Kokoro re-downloads weights every container restart (~300 MB) |

---

## Out of scope / explicitly not here

- **Wake-word *detection*** — that's on the node (porcupine, etc.)
- **STT** — see `jarvis-whisper-api`
- **Prompt building** — command-center owns prompts. The deprecated `/generate-wake-response` shim is the only exception and is on its way out
- **Voice training** — providers ship pre-trained voices; this service doesn't fine-tune
- **Voice cloning / SSML** — not supported by either provider
