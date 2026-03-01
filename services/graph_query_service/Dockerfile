# ─── Stage 1: builder ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt


# ─── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Non-root user for security
RUN groupadd --system appgroup && useradd --system --gid appgroup appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy shared library and service code
COPY shared/ ./shared/
COPY services/graph_query_service/ ./services/graph_query_service/

# Ensure services package is importable
RUN touch services/__init__.py

# Environment defaults (overridden at runtime via env vars / secrets)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    ENVIRONMENT=production \
    PORT=8002

# Drop to non-root
USER appuser

EXPOSE 8002

# Healthcheck — hit the liveness endpoint every 30 s
# Uses ${PORT} which defaults to 8002 via the ENV above.
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:' + __import__('os').environ.get('PORT','8002') + '/health')"

# Start the service
# Use sh -c so the shell expands ${PORT:-8002} at container start time.
# Railway injects PORT; the :-8002 fallback keeps local Docker working.
CMD ["sh", "-c", \
     "python -m uvicorn \
          services.graph_query_service.main:app \
          --host 0.0.0.0 \
          --port ${PORT:-8002} \
          --workers ${WEB_CONCURRENCY:-2} \
          --log-level info"]
