FROM python:3.11-slim-bullseye

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# --- Python deps -------------------------------------------------------
# We keep requirements.txt under app/ and copy it into the image
COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# --- App code ----------------------------------------------------------
COPY . /app

ENV VERIRECEIPT_STORE_BACKEND=db
ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "9000"]