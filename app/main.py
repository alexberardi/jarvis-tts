import json
import logging
import os
import re
import wave
from io import BytesIO

import httpx
import onnxruntime as ort
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import StreamingResponse

from app import service_config
from app.deps import verify_app_auth
from app.providers.base import TTSProvider
from app.services.provider_manager import get_active_provider
from app.services.settings_service import get_settings_service
from jarvis_auth_client.models import AppAuthResult
from jarvis_settings_client import create_combined_auth, create_settings_router, create_superuser_auth

try:
    from jarvis_log_client import JarvisLogHandler, init as init_log_client
    _jarvis_log_available = True
except ImportError:
    _jarvis_log_available = False

ort.set_default_logger_severity(3)  # 3=ERROR, suppresses warnings
load_dotenv()

console_level = os.getenv("JARVIS_LOG_CONSOLE_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, console_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("uvicorn")

_jarvis_handler = None


def _setup_remote_logging() -> None:
    """Set up remote logging to jarvis-logs server."""
    global _jarvis_handler

    if not _jarvis_log_available:
        logger.debug("jarvis-log-client not installed, remote logging disabled")
        return

    app_id = os.getenv("JARVIS_APP_ID", "jarvis-tts")
    app_key = os.getenv("JARVIS_APP_KEY")
    if not app_key:
        logger.warning("JARVIS_APP_KEY not set, remote logging disabled")
        return

    init_log_client(app_id=app_id, app_key=app_key)

    remote_level = os.getenv("JARVIS_LOG_REMOTE_LEVEL", "DEBUG")
    _jarvis_handler = JarvisLogHandler(
        service="jarvis-tts",
        level=getattr(logging, remote_level.upper(), logging.DEBUG),
    )

    for logger_name in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
        logging.getLogger(logger_name).addHandler(_jarvis_handler)

    logger.info("Remote logging enabled to jarvis-logs")


app = FastAPI(title="Jarvis TTS", version="1.0.0")

_settings_router = create_settings_router(
    service=get_settings_service(),
    auth_dependency=create_combined_auth(service_config.get_auth_url()),
    write_auth_dependency=create_superuser_auth(service_config.get_auth_url()),
)
app.include_router(_settings_router, prefix="/settings", tags=["settings"])


@app.on_event("startup")
async def startup_event():
    """Initialize services on app startup."""
    service_config.init()
    _setup_remote_logging()
    # Warm up the default provider so the first /speak request doesn't pay
    # the model-load cost. If it fails we still start — the manager will
    # fall back to Piper on the first real request.
    try:
        provider = get_active_provider()
        logger.info(f"TTS ready with provider '{provider.name}'")
    except Exception as e:
        logger.warning(f"Failed to pre-load TTS provider at startup: {e}")
    logger.info("Jarvis TTS service started")


@app.get("/ping")
def pong():
    return {"message": "pong"}


@app.get("/audio/format")
def audio_format(
    auth: AppAuthResult = Depends(verify_app_auth),
    provider: TTSProvider = Depends(get_active_provider),
):
    """Return the current provider's audio format (no synthesis needed)."""
    fmt = provider.get_audio_format()
    return {
        "sample_rate": fmt.sample_rate,
        "channels": fmt.channels,
        "sample_width": fmt.sample_width,
        "provider": provider.name,
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/speak")
async def speak(
    request: Request,
    auth: AppAuthResult = Depends(verify_app_auth),
    provider: TTSProvider = Depends(get_active_provider),
):
    logger.debug(
        f"TTS request from {auth.app.app_id} "
        f"for household {auth.context.household_id}, node {auth.context.node_id} "
        f"(provider={provider.name})"
    )
    data = await request.json()
    text = data.get("text", "")
    if not text:
        return {"error": "No text provided"}

    fmt = provider.get_audio_format()
    buf = BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(fmt.channels)
        wav_file.setsampwidth(fmt.sample_width)
        wav_file.setframerate(fmt.sample_rate)
        for chunk in provider.synthesize(text):
            wav_file.writeframes(chunk.audio_bytes)

    return Response(content=buf.getvalue(), media_type="audio/wav")


@app.post("/speak/stream")
async def speak_stream(
    request: Request,
    auth: AppAuthResult = Depends(verify_app_auth),
    provider: TTSProvider = Depends(get_active_provider),
):
    """Stream raw PCM audio chunks for low-latency playback.

    Returns raw 16-bit PCM (no WAV header). Audio format metadata is in
    response headers so the client can initialize its playback pipeline.
    """
    logger.debug(
        f"TTS stream request from {auth.app.app_id} "
        f"for household {auth.context.household_id}, node {auth.context.node_id} "
        f"(provider={provider.name})"
    )
    data = await request.json()
    text = data.get("text", "")
    if not text:
        return {"error": "No text provided"}

    fmt = provider.get_audio_format()

    def pcm_generator():
        for chunk in provider.synthesize(text):
            yield chunk.audio_bytes

    return StreamingResponse(
        pcm_generator(),
        media_type="audio/raw",
        headers={
            "X-Audio-Sample-Rate": str(fmt.sample_rate),
            "X-Audio-Channels": str(fmt.channels),
            "X-Audio-Sample-Width": str(fmt.sample_width),
            "X-Audio-Provider": provider.name,
        },
    )


_WAKE_RESPONSE_FALLBACK = "Yes?"

# Strip Qwen3-style <think>...</think> blocks from LLM responses that leak
# through when the /no_think control token is ignored. Cheap enough to run
# on every response; no-op for models that don't emit these.
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


@app.post("/generate-wake-response")
async def generate_wake_response(auth: AppAuthResult = Depends(verify_app_auth)):
    logger.debug(
        f"Wake response request from {auth.app.app_id} "
        f"for household {auth.context.household_id}, node {auth.context.node_id}"
    )

    # OpenAI-compatible chat endpoint on jarvis-llm-proxy-api. Requires
    # X-Jarvis-App-Id + X-Jarvis-App-Key (same creds we already use for
    # remote logging). Fallback to a static "Yes?" if the call fails so
    # the node always gets something usable.
    llm_proxy_url = f"{service_config.get_llm_proxy_url().rstrip('/')}/v1/chat/completions"
    app_id = os.getenv("JARVIS_APP_ID", "jarvis-tts")
    app_key = os.getenv("JARVIS_APP_KEY", "")

    system_prompt = (
        "You are Jarvis, a voice assistant butler. The user has just called you for help. "
        "Please keep the greeting gender neutral. Please keep the greeting to one or two short sentences, but make it charming."
        "The entire response should be less than 10 words if possible."
        "Generate a short greeting like 'At your service', 'How may I help you?', etc."
    )

    headers = {
        "Content-Type": "application/json",
        "X-Jarvis-App-Id": app_id,
        "X-Jarvis-App-Key": app_key,
    }
    body = {
        "model": "live",
        "messages": [
            {"role": "system", "content": system_prompt},
            # /no_think disables Qwen3 thinking mode (ignored by models that
            # don't recognize it, so this is safe across providers).
            {"role": "user", "content": "Hello Jarvis\n/no_think"},
        ],
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(llm_proxy_url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
            choices = data.get("choices") or []
            if choices:
                content = (choices[0].get("message") or {}).get("content", "") or ""
                # Defense-in-depth: strip Qwen3 <think>...</think> blocks in
                # case /no_think was ignored. Adds ~500 tokens of wasted
                # decode per response when these leak through.
                content = _THINK_BLOCK_RE.sub("", content)
                text = content.strip()
                if text:
                    return {"text": text}
            logger.warning("LLM proxy returned no wake-response text; using fallback")
    except httpx.HTTPStatusError as e:
        logger.error(
            "LLM proxy returned %s for wake-response: %s",
            e.response.status_code,
            e.response.text[:200],
        )
    except (httpx.RequestError, json.JSONDecodeError, KeyError, IndexError) as e:
        logger.error("Wake-response generation failed: %s", e)

    return {"text": _WAKE_RESPONSE_FALLBACK}
