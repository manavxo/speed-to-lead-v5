FROM python:3.12-slim

WORKDIR /app

# Install system deps for psycopg3 binary
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

# Render injects PORT; default to 10000 for local Docker runs
ENV PORT=10000
EXPOSE ${PORT}

# Use shell form so $PORT is interpolated
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
