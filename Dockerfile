FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    sox \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

# Copy app and models
COPY app /app/app

# Download Piper model and config from csukuangfj's repo
RUN mkdir -p /app/app/models && \
    wget https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_GB/alan/low/en_GB-alan-low.onnx?download=true \
         -O /app/app/models/en_GB-alan-low.onnx && \
    wget https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_GB/alan/low/en_GB-alan-low.onnx.json?download=true.json \
         -O /app/app/models/en_GB-alan-low.onnx.json

VOLUME /tmp
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

