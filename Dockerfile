FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    git \
    sox \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Copy app and models
COPY app /app/app

# Install Python deps
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Download Piper model and config from csukuangfj's repo
RUN mkdir -p /app/app/models && \
    wget https://huggingface.co/csukuangfj/vits-piper-en_GB-alan-low/resolve/main/en_GB-alan-low.onnx \
         -O /app/app/models/en_GB-alan-low.onnx && \
    wget https://huggingface.co/csukuangfj/vits-piper-en_GB-alan-low/resolve/main/en_GB-alan-low.onnx.json \
         -O /app/app/models/en_GB-alan-low.onnx.json

VOLUME /tmp

ENV TTS_PORT=7707
CMD uvicorn app.main:app --host 0.0.0.0 --port ${TTS_PORT}

