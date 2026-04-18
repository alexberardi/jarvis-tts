# PRD: Multi-Provider TTS Support

## Goal

Add Kokoro TTS as a provider option alongside existing Piper TTS. Users select providers via the settings service. Kokoro should feel natural and fluid — a major upgrade from Piper's robotic long-form output.

F5-TTS was considered but deferred: it lacks true real-time streaming (buffers per text chunk before yielding), has high first-audio latency, and needs a concrete voice-cloning use case to justify the GPU cost. Revisit later if needed.

## Current State

jarvis-tts is **hardcoded to Piper TTS** with no provider abstraction:
- Single global `PiperVoice` instance loaded at module level in `app/main.py`
- Endpoints call `voice.synthesize(text)` directly
- Voice model downloaded at Docker build time (`en_GB-alan-low.onnx`, 63MB)
- Output: 16-bit PCM, 22050 Hz, mono

There is NO provider interface, factory, or registry. Adding providers requires refactoring `main.py`.

## Architecture

### Provider Interface

Create `app/providers/base.py`:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generator

@dataclass(frozen=True)
class AudioFormat:
    sample_rate: int
    sample_width: int  # bytes per sample (2 = 16-bit)
    channels: int

@dataclass
class AudioChunk:
    audio_bytes: bytes
    format: AudioFormat

class TTSProvider(ABC):
    """Abstract base for TTS providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for settings/logging."""
        ...

    @abstractmethod
    def synthesize(self, text: str) -> Generator[AudioChunk, None, None]:
        """Yield audio chunks for the given text."""
        ...

    @abstractmethod
    def get_audio_format(self) -> AudioFormat:
        """Return audio format metadata for this provider."""
        ...

    def is_available(self) -> bool:
        """Check if this provider is ready (model loaded, etc.)."""
        return True
```

Typed `AudioFormat` dataclass is preferred over `dict[str, Any]` for clarity and type-safety.

### Provider Implementations

#### `app/providers/piper_provider.py` (refactor existing)

Extract current Piper logic from `main.py`:
- Load `PiperVoice` from ONNX model path
- `synthesize()` wraps `voice.synthesize(text)`, yields `AudioChunk`
- Model path configurable via `tts.piper_model_path` setting
- Voice selection via `tts.piper_voice` setting (default: `en_GB-alan-low`)
- Audio format: 22050 Hz, 16-bit, mono

#### `app/providers/kokoro_provider.py` (new)

[Kokoro TTS](https://github.com/hexgrad/kokoro) — 82M param Apache 2.0 model. Natural prosody, true streaming via `KPipeline` generator (yields per-segment chunks, ~550ms time-to-first-audio).

- Install: `pip install kokoro soundfile`
- Streaming: `KPipeline(lang_code='b')(text, voice='bm_george')` returns a generator yielding `(graphemes, phonemes, audio)` tuples — wrap each as `AudioChunk`
- Runs on CPU (~2-3x realtime) or GPU (fast). CPU is acceptable for our throughput
- Default sample rate: 24000 Hz
- Configuration:
  - `tts.kokoro_voice` — voice/style selection (default: `bm_george`, a British male voice)
  - `tts.kokoro_speed` — speech speed multiplier (default: `1.0`)
- Alternative UK male voices to A/B test: `bm_fable`, `bm_daniel`, `bm_lewis`. Community ranks `bm_george` and `bm_fable` highest

### Model Distribution (Runtime Download + Cache)

Do NOT bake Kokoro models into the Docker image. Instead:
- Kokoro auto-downloads weights via `huggingface_hub` on first use
- Cache directory: `HF_HOME=/app/models/hf_cache` (mount as Docker volume to persist across restarts)
- Piper stays baked into the image (small, lightweight fallback — see below)

### Provider Registry & Fallback

Create `app/providers/registry.py`:

```python
_PROVIDERS: dict[str, type[TTSProvider]] = {}

def register(name: str, cls: type[TTSProvider]):
    _PROVIDERS[name] = cls

def get_provider(name: str, **kwargs) -> TTSProvider:
    cls = _PROVIDERS.get(name)
    if not cls:
        raise ValueError(f"Unknown TTS provider: {name}")
    return cls(**kwargs)

# Auto-register on import
from .piper_provider import PiperTTSProvider
register("piper", PiperTTSProvider)

try:
    from .kokoro_provider import KokoroTTSProvider
    register("kokoro", KokoroTTSProvider)
except ImportError:
    pass  # kokoro not installed
```

**Fallback behavior**: If the selected provider fails to instantiate or load (import error, missing model, runtime exception), log a warning and fall back to Piper. Piper is always available because its model is baked into the image.

```python
def load_active_provider(name: str) -> TTSProvider:
    try:
        return get_provider(name)
    except Exception as e:
        logger.warning(f"Failed to load provider '{name}': {e}. Falling back to Piper.")
        return get_provider("piper")
```

### Settings

Add to `app/services/settings_definitions.py`:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `tts.provider` | string | `kokoro` | Active provider: `piper`, `kokoro` |
| `tts.kokoro_voice` | string | `bm_george` | Kokoro voice (e.g., `bm_george`, `bm_fable`, `af_heart`) |
| `tts.kokoro_speed` | float | `1.25` | Kokoro speed multiplier (validated natural-sounding default) |

### Settings Polling & Live Reload

The service polls settings every **60 seconds** and caches the current provider instance. If `tts.provider` or any provider-specific setting changes, the service lazily reloads on the next synthesis request. No container restart required.

Implementation sketch:
- Background task polls settings via jarvis-settings-client every 60s
- When a TTS-relevant setting changes, mark the cached provider as stale
- Next request to `/speak` re-instantiates the provider (loading model if needed)
- Avoid blocking requests during reload: if reload fails, keep the previous provider and log a warning

### Endpoint Changes

Refactor `app/main.py`:
- Replace global `voice = PiperVoice.load(...)` with provider loading via registry
- Use `Depends(get_active_provider)` in endpoints
- `/speak` and `/speak/stream` call `provider.synthesize(text)` instead of `voice.synthesize(text)`
- Audio format headers come from `provider.get_audio_format()` (each provider may have different sample rates)

### Audio Format Normalization

Different providers output different sample rates:
- Piper: 22050 Hz
- Kokoro: 24000 Hz

The endpoints already send audio format in response headers (`X-Audio-Sample-Rate`, etc.). The node's `play_pcm_stream()` reads these headers and passes them to aplay. Format differences are handled automatically — no resampling needed.

### Dockerfile

Keep Piper's ONNX model baked in at build time (lightweight, always-available fallback). Kokoro models download at runtime.

```dockerfile
FROM python:3.12-slim

# Piper models (baked in — lightweight fallback)
RUN wget -q ... -O app/models/en_GB-alan-low.onnx
RUN wget -q ... -O app/models/en_GB-alan-low.onnx.json

# Kokoro cache directory (volume mount persists weights across restarts)
ENV HF_HOME=/app/models/hf_cache
RUN mkdir -p /app/models/hf_cache
```

Add a volume for `HF_HOME` in docker-compose so Kokoro weights aren't re-downloaded on every container restart.

### pyproject.toml

```toml
[project.optional-dependencies]
kokoro = ["kokoro>=0.8", "soundfile"]
```

Install with `pip install ".[kokoro]"` to enable Kokoro. Without it, only Piper is available.

## Implementation Order

1. Create `app/providers/` package with `base.py` (TTSProvider interface + AudioFormat/AudioChunk dataclasses)
2. Extract `app/providers/piper_provider.py` from existing `main.py` logic
3. Create `app/providers/registry.py` with fallback-to-Piper logic
4. Refactor `main.py` to use registry + provider interface
5. Add settings definitions for `tts.provider`, `tts.kokoro_voice`, `tts.kokoro_speed`
6. Add 60s settings polling + lazy provider reload
7. Implement `app/providers/kokoro_provider.py` with streaming `KPipeline` wrapper
8. Update `pyproject.toml` with optional `kokoro` dep
9. Update Dockerfile: add `HF_HOME` env + volume mount for weight cache
10. Test: switch providers via settings, verify audio output, A/B test `bm_george` vs `bm_fable`

## Testing

- Verify Piper still works after refactor (regression)
- Test Kokoro: `tts.provider=kokoro`, speak a long paragraph, verify natural prosody
- Test voice swap: change `tts.kokoro_voice` from `bm_george` → `bm_fable`, verify new voice is used within 60s
- Test fallback: set `tts.provider=kokoro` with `kokoro` package uninstalled → verify Piper is used and warning is logged
- Test settings polling: change `tts.provider` via settings API → verify new provider is used without container restart
- Test audio format headers: each provider reports correct sample_rate
- Test weight caching: restart container, verify Kokoro doesn't re-download weights

## Key Files

| File | Action |
|------|--------|
| `app/providers/__init__.py` | New package |
| `app/providers/base.py` | TTSProvider abstract class + AudioFormat/AudioChunk dataclasses |
| `app/providers/piper_provider.py` | Extract from main.py |
| `app/providers/kokoro_provider.py` | New provider |
| `app/providers/registry.py` | Provider registry + auto-registration + fallback |
| `app/main.py` | Refactor to use provider interface |
| `app/services/settings_definitions.py` | Add provider settings |
| `app/services/settings_poller.py` | New — 60s polling + lazy provider reload |
| `pyproject.toml` | Optional `kokoro` dependency |
| `Dockerfile` | Add `HF_HOME` env + cache directory |
| `docker-compose.yaml` | Add volume mount for Kokoro weight cache |
