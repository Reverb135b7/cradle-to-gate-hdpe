# OpenCarbonChem — HDPE PCF / LCA dashboard
# Build once, run anywhere that can run a Python uvicorn service.

FROM python:3.12-slim AS base

WORKDIR /app

# Build deps first so the app layer rebuilds only when deps change.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application source. Do not copy artefacts that are ephemeral or
# platform-specific: outputs/, app/_generated/, *.pdf, *.pptx, *.xlsx,
# *.png and the openLCA IPC runtime are intentionally left out of the image.
COPY . .

# The mounted generated-output directory must exist and be writable at
# runtime. On Render this is backed by a persistent disk; in local docker
# or other hosts you can bind-mount one or leave it ephemeral.
RUN mkdir -p /app/app/_generated && chmod 777 /app/app/_generated

ENV PYTHONUNBUFFERED=1 \
    GENERATED_DIR=/app/app_/generated \
    HOST=0.0.0.0 \
    PORT=8000

EXPOSE 8000

# The host/port here is a safe local default only. In production the
# platform should override HOST/PORT and mount GENERATED_DIR.
CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8000"]
