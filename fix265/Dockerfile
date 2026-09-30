FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Europe/Paris

WORKDIR /app

# Bibliothèques natives utilisées par Pillow / pyvips / Pango / Cairo.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    tesseract-ocr \
    tesseract-ocr-eng tesseract-ocr-fra tesseract-ocr-deu tesseract-ocr-spa tesseract-ocr-por \
    tesseract-ocr-rus tesseract-ocr-ukr tesseract-ocr-ara tesseract-ocr-chi-sim tesseract-ocr-jpn tesseract-ocr-kor \
    tzdata \
    libvips42 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libglib2.0-0 \
    libgdk-pixbuf-2.0-0 \
    libjpeg62-turbo \
    libpng16-16 \
    libwebp7 \
    libffi8 \
    shared-mime-info \
    fonts-dejavu-core \
    fonts-noto-core \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install -r requirements.txt

COPY . .

# Toutes les données persistantes Legacy sont écrites dans /app/data
# (legacy.sqlite3, hub_message.json, rendus d'expédition, etc.).
RUN mkdir -p /app/data

CMD ["python", "-u", "main.py"]
