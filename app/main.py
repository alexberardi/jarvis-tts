from fastapi import FastAPI, Request, Response
from piper import PiperVoice
from pathlib import Path
from io import BytesIO
import wave
from dotenv import load_dotenv
import os
import httpx
load_dotenv()

app = FastAPI()

VOICE_DIR = Path("app/models")
MODEL_PATH = VOICE_DIR / "en_GB-alan-low.onnx"
CONFIG_PATH = VOICE_DIR / "en_GB-alan-low.onnx.json"

voice = PiperVoice.load(model_path=MODEL_PATH, config_path=CONFIG_PATH)

@app.get("/ping")
def pong():
    return {"message": "pong"}

@app.post("/speak")
async def speak(request: Request):
    data = await request.json()
    text = data.get("text", "")
    if not text:
        return {"error": "No text provided"}

    # Get the generator from Piper
    audio_chunks = voice.synthesize(text)

    # Grab first chunk to read audio properties
    first_chunk = next(audio_chunks)
    sample_rate = first_chunk.sample_rate
    channels = first_chunk.sample_channels
    sample_width = first_chunk.sample_width  # in bytes (should be 2 for 16-bit PCM)

    # Prepare in-memory WAV buffer
    buf = BytesIO()
    with wave.open(buf, 'wb') as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)

        # Write first chunk
        wav_file.writeframes(first_chunk.audio_int16_bytes)

        # Write remaining chunks
        for chunk in audio_chunks:
            wav_file.writeframes(chunk.audio_int16_bytes)

    return Response(content=buf.getvalue(), media_type="audio/wav")

@app.post("/generate-wake-response")
async def generate_wake_response():
    llm_proxy_version = os.getenv("JARVIS_LLM_PROXY_API_VERSION")
    llm_proxy_url = f"{os.getenv('JARVIS_LLM_PROXY_API_URL')}/api/v{llm_proxy_version}/lightweight/chat"
    print(llm_proxy_url)
    
    system_prompt = (
        "You are Jarvis, a voice assistant butler. The user has just called you for help. "
        "Please keep the greeting gender neutral. Please keep the greeting to one or two short sentences, but make it charming."
        "The entire response should be less than 10 words if possible."
        "Generate a short greeting like 'At your service', 'How may I help you?', etc."
    )

    headers = {"Content-Type": "application/json"}
    body = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Hello Jarvis"}
        ],
        "stream": True
    }

    async with httpx.AsyncClient() as client:
        async with client.stream("POST", llm_proxy_url, headers=headers, json=body, timeout=20.0) as response:
            response.raise_for_status()
            full_text = ""
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                try:
                    chunk = httpx.Response(200, content=line).json()
                    full_text += chunk.get("response", "")
                except Exception:
                    continue

    return {"text": full_text.strip() or "Yes?"}
