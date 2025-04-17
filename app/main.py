from fastapi import FastAPI, Request, Response
import subprocess
from pathlib import Path

app = FastAPI()

OUTPUT_FILE = Path("/tmp/tts.wav")
MODEL_PATH = "app/models/en_GB-alan-low.onnx"

@app.post("/speak")
async def speak(request: Request):
    data = await request.json()
    text = data.get("text", "")
    if not text:
        return {"error": "No text provided"}

    # Generate TTS audio
    subprocess.run([
        "piper",
        "--model", MODEL_PATH,
        "--text", text,
        "--output_file", str(OUTPUT_FILE)
    ], check=True)

    # Read and return the WAV audio directly
    audio_bytes = OUTPUT_FILE.read_bytes()
    return Response(content=audio_bytes, media_type="audio/wav")

