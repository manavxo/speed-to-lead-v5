# Speed-to-Lead v4 — Production Dockerfile
# Single container: web server + background scheduler (via FastAPI lifespan)

FROM python:3.12-slim AS base

# System deps for psycopg (Postgres driver)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install deps first (layer caching)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ app/
COPY tools/ tools/
COPY workflows/ workflows/
COPY dealers/ dealers/
COPY landing/ landing/
COPY start.sh ./
RUN chmod +x start.sh

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/healthz || exit 1

EXPOSE 8000

CMD ["./start.sh"]
