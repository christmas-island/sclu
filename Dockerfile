FROM python:3.12-slim

# System deps for pyzbar (libzbar0), opencv (libgl1, libglib2.0), and OCR (tesseract)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libzbar0 \
    libgl1 \
    libglib2.0-0 \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py sclu.py ./

CMD ["python", "bot.py"]
