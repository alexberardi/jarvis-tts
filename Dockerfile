FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt update && apt install -y espeak-ng libespeak-ng1 sox

# Install Python deps
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy Piper model and app
COPY app ./app
COPY static ./static

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

