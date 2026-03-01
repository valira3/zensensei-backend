# ────────────────────────────────────────────────────────────────────────────────
# ZenSensei Analytics Service — Dockerfile
# ────────────────────────────────────────────────────────────────────────────────
# Multi-stage build:
#   builder  — installs Python dependencies into a virtual-env
#   runtime  — copies only the venv + application code for a slim final image
# ────────────────────────────────────────────────────────────────────────────────

# ── Stage 1: dependency builder ─────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

# Install build tools required by some native wheels (e.g. bcrypt, orjson)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Create and activate a virtual-env so we can COPY just the site-packages later
RUN python -m venv /build/venv
ENV PATH="/build/venv/bin:$PATH"

# Copy only requirement files first to leverage Docker layer caching
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# ── Stage 2: runtime image ──────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Non-root user for security
RUN groupadd --gid 1001 zensensei && \
    useradd --uid 1001 --gid zensensei --shell /bin/bash --create-home zensensei

WORKDIR /app

# Copy virtual-env from builder
COPY --from=builder /build/venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

# Copy the shared library and the service code
COPY shared/ ./shared/
COPY services/analytics_service/ ./services/analytics_service/

# Ensure the services package is importable (no pyproject.toml install needed)
ENV PYTHONPATH="/app:$PYTHONPATH"

# Runtime configuration
ENV ENVIRONMENT=production \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8006

EXPOSE 8006

USER zensensei

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:' + __import__('os').environ.get('PORT','8006') + '/health')"

CMD ["sh", "-c", \
     "uvicorn \
          services.analytics_service.main:app \
          --host 0.0.0.0 \
          --port ${PORT:-8006} \
          --workers ${WEB_CONCURRENCY:-2} \
          --log-level info \
          --access-log"]
