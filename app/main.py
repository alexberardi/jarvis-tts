from fastapi import FastAPI, Request, Response
from piper import PiperVoice
from pathlib import Path
from io import BytesIO
import wave

app = FastAPI()

VOICE_DIR = Path("app/models")
MODEL_PATH = VOICE_DIR / "en_GB-alan-low.onnx"
CONFIG_PATH = VOICE_DIR / "en_GB-alan-low.onnx.json"

voice = PiperVoice.load(model_path=MODEL_PATH, config_path=CONFIG_PATH)

@app.post("/speak")
async def speak(request: Request):
    data = await request.json()
    text = data.get("text", "")
    if not text:
        return {"error": "No text provided"}

    buf = BytesIO()
    with wave.open(buf, 'wb') as wav_file:
        voice.synthesize(text, wav_file=wav_file)
    audio_bytes = buf.getvalue()

    return Response(content=audio_bytes, media_type="audio/wav")

