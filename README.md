# Jarvis TTS

A FastAPI-based text-to-speech service using Piper TTS for the Jarvis voice assistant project.

## Features

- Text-to-speech synthesis using Piper TTS
- Wake word response generation via LLM proxy
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
5. Run the application: `uvicorn app.main:app --host 0.0.0.0 --port 8000`

## Docker

Build and run with Docker:

```bash
docker build -t jarvis-tts .
docker run -p 8000:8000 jarvis-tts
```

## Usage

### Text-to-Speech
```bash
curl -X POST "http://localhost:8000/speak" \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello, I am Jarvis"}'
```

### Generate Wake Response
```bash
curl -X POST "http://localhost:8000/generate-wake-response"
```

## Requirements

- Python 3.8+
- Piper TTS
- FastAPI
- httpx
- python-dotenv 