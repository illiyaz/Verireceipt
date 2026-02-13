FROM python:3.11-slim-bullseye

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# --- System deps needed by Python packages ----------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx libglib2.0-0 \
    tesseract-ocr \
    poppler-utils \
    libmagic1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# --- Python deps -------------------------------------------------------
# We keep requirements.txt under app/ and copy it into the image
COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# --- App code ----------------------------------------------------------
COPY . /app

ENV VERIRECEIPT_STORE_BACKEND=db
ENV PYTHONUNBUFFERED=1

EXPOSE ${PORT:-9000}
CMD uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-9000}