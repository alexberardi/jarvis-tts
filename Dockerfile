# Pinned by digest. Upstream tags (python:3.11-slim, nvidia/cuda) push
# silent updates that can ABI-break native deps; the jarvis-whisper-api
# v0.1.12 build picked up a newer cuBLAS rev that SIGILL'd whisper.cpp.
# This is the digest the currently-deployed prod TTS image was built
# against. Bump deliberately, not via tag drift. To refresh:
#   docker buildx imagetools inspect python:3.11-slim
FROM python:3.11-slim@sha256:a3ab0b966bc4e91546a033e22093cb840908979487a9fc0e6e38295747e49ac0

WORKDIR /app

RUN apt-get update && apt-get install -y \
    git \
    sox \
    wget \
    espeak-ng \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Copy app
COPY app /app/app

# Alembic migrations. The stack provisions a service's settings DB by flagging
# `migrate: true` in the service registry, which makes the compose generator wrap
# the container in an entrypoint that runs `python -m alembic upgrade head` before
# the app CMD. That requires the migration env + versions to be present in the
# image (matches jarvis-whisper-api). Without this, tts has no settings table and
# every persisted settings write fails (reads silently fall back to env vars).
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini

# Install Python deps. The `kokoro` extra pulls in kokoro + soundfile;
# pin the extra in the build (see docker-compose to disable on low-mem hosts).
COPY pyproject.toml .

# Optional: pre-install torch from a non-default wheel index (e.g. the
# CUDA-enabled wheels) BEFORE the kokoro extra. When TORCH_INDEX_URL is
# set, pip picks up that torch and the kokoro install resolves against
# it instead of pulling the default CPU wheel. Default empty = CPU torch,
# matching the existing behavior. See docker-compose.gpu.yaml.
ARG TORCH_INDEX_URL=""
RUN if [ -n "$TORCH_INDEX_URL" ]; then \
      pip install --no-cache-dir --index-url "$TORCH_INDEX_URL" torch; \
    fi

ARG INSTALL_EXTRAS="kokoro"
RUN if [ -n "$INSTALL_EXTRAS" ]; then \
      pip install --no-cache-dir ".[${INSTALL_EXTRAS}]"; \
    else \
      pip install --no-cache-dir .; \
    fi

# Bake Piper model — always available as the fallback provider.
RUN mkdir -p /app/app/models && \
    wget https://huggingface.co/csukuangfj/vits-piper-en_GB-alan-low/resolve/main/en_GB-alan-low.onnx \
         -O /app/app/models/en_GB-alan-low.onnx && \
    wget https://huggingface.co/csukuangfj/vits-piper-en_GB-alan-low/resolve/main/en_GB-alan-low.onnx.json \
         -O /app/app/models/en_GB-alan-low.onnx.json

# Kokoro downloads voice weights to HF_HOME on first use. Mount a volume
# at this path in docker-compose so weights persist across container
# restarts (otherwise each cold start re-downloads ~300MB).
ENV HF_HOME=/app/models/hf_cache
RUN mkdir -p /app/models/hf_cache

VOLUME /tmp
VOLUME /app/models/hf_cache

ENV TTS_PORT=7707
CMD uvicorn app.main:app --host 0.0.0.0 --port ${TTS_PORT}
