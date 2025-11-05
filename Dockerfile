# ================================
# MatchMyStack - Dockerfile (multi-stage, smaller final image)
# ================================

### ---------- Builder stage ----------
FROM python:3.10-slim AS builder
ENV DEBIAN_FRONTEND=noninteractive

# Install build tools and libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libpq-dev \
    libssl-dev \
    libffi-dev \
    python3-dev \
    pkg-config \
    curl \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements from current folder (Dockerfile is in backend/)
COPY requirements.txt ./requirements.txt

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip tooling and install deps
RUN pip install --no-cache-dir --upgrade pip setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY . .

### ---------- Runtime stage ----------
FROM python:3.10-slim
ENV DEBIAN_FRONTEND=noninteractive
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app

RUN mkdir -p /data/uploads && chown -R www-data:www-data /data/uploads || true

EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
