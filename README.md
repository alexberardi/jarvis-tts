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
2. Install dependencies: `pip install -r requirements.txt`
3. Set up environment variables in `.env` file:
   ```
   JARVIS_LLM_PROXY_API_URL=your_llm_proxy_url
   JARVIS_LLM_PROXY_API_VERSION=your_api_version
   ```
4. Download the required voice models to `app/models/`
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

- Python 3.8+
- Piper TTS (always installed; baked-in ONNX voice)
- Kokoro (optional; pulled in by the default `INSTALL_EXTRAS=kokoro` Docker build, weights downloaded on first use to `HF_HOME`)
- FastAPI
- httpx
- python-dotenv 