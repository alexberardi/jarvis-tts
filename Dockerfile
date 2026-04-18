FROM python:3.11-slim

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

# Install Python deps. The `kokoro` extra pulls in kokoro + soundfile;
# pin the extra in the build (see docker-compose to disable on low-mem hosts).
COPY pyproject.toml .
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
