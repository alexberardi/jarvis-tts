# Jarvis TTS

A FastAPI-based text-to-speech service for the Jarvis voice assistant project, with two interchangeable providers: **Piper** (fast, baked into the image) and **Kokoro** (higher-quality, downloaded on first use). Provider selection is settings-driven with live hot-swap; failed loads fall back to Piper so the service never goes silent.

## Features

- Text-to-speech synthesis via Piper or Kokoro (selectable at runtime)
- Streaming raw PCM output for low-latency playback, plus buffered WAV
- Wake word response generation via LLM proxy (deprecated shim — new callers should use `jarvis-command-center /api/v0/wake-response`)
- Docker containerization
- RESTful API endpoints

## API Endpoints

- `GET /ping` - Health check endpoint
- `POST /speak` - Convert text to speech
- `POST /generate-wake-response` - Generate a wake word response

## Setup

1. Clone the repository
2. Install dependencies (PEP 621 / setuptools project — no `requirements.txt`):
   ```bash
   pip install -e .            # base deps
   pip install -e ".[kokoro]"  # optional Kokoro provider
   ```
   (Or just run `./run.sh --setup`, which creates a venv and installs the project plus the Kokoro extra.)
3. Set up environment variables in `.env` file:
   ```
   JARVIS_LLM_PROXY_API_URL=your_llm_proxy_url
   JARVIS_LLM_PROXY_API_VERSION=your_api_version
   ```
4. The Piper voice model is **not committed** — it is fetched on first run, the
   same way Kokoro weights are. The Docker build downloads it automatically
   (see the `wget` step in the `Dockerfile`). For a native/local run, download
   the voice pair into `app/models/` once:
   ```bash
   mkdir -p app/models
   wget https://huggingface.co/csukuangfj/vits-piper-en_GB-alan-low/resolve/main/en_GB-alan-low.onnx \
        -O app/models/en_GB-alan-low.onnx
   wget https://huggingface.co/csukuangfj/vits-piper-en_GB-alan-low/resolve/main/en_GB-alan-low.onnx.json \
        -O app/models/en_GB-alan-low.onnx.json
   ```
5. Run the application: `uvicorn app.main:app --host 0.0.0.0 --port 7707`

## Docker

Build and run with Docker:

```bash
docker build -t jarvis-tts .
docker run -p 7707:7707 jarvis-tts
```

## Usage

### Text-to-Speech
```bash
curl -X POST "http://localhost:7707/speak" \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello, I am Jarvis"}'
```

### Generate Wake Response
```bash
curl -X POST "http://localhost:7707/generate-wake-response"
```

## Requirements

- Python 3.11+
- Piper TTS (always installed; ONNX voice baked into the Docker image at build time, downloaded on first run for native setups — see Setup step 4)
- Kokoro (optional; pulled in by the default `INSTALL_EXTRAS=kokoro` Docker build, weights downloaded on first use to `HF_HOME`)
- FastAPI
- httpx
- python-dotenv 