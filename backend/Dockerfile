FROM python:3.12-slim

WORKDIR /app

# System deps: image processing (rembg/pillow/playwright basics + opencv runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Python deps first (caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir litellm google-generativeai

# litellm and google-generativeai are imported at runtime; install explicitly so
# image builds don't depend on running the API call to discover them.

COPY app ./app
COPY cli ./cli
COPY gramnsap ./gramnsap

# Data dir is mounted as a volume from host (/var/app/data → /app/data)
ENV DATA_DIR=/app/data
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
