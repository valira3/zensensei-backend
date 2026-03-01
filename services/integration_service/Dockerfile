# ──────────────────────────────────────────────────────────────────────────────
# ZenSensei Integration Service - Dockerfile
# ──────────────────────────────────────────────────────────────────────────────
# Multi-stage build: slim Python 3.12 base → non-root runtime
# Port: 8004
# ──────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Dependency builder ──────────────────────────────────────────────────────

FROM python:3.12-slim AS builder

WORKDIR /build

# System deps needed to compile native extensions (e.g. bcrypt, orjson)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies into a separate prefix so we can
# copy only the installed packages into the final stage.
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --prefix=/install --no-cache-dir -r requirements.txt


# ── Stage 2: Runtime image ────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL maintainer="ZenSensei Platform Team <platform@zensensei.net>"
LABEL service="integration-service"
LABEL version="1.0.0"

# Security: non-root user
RUN groupadd --gid 1001 zensensei \
    && useradd --uid 1001 --gid zensensei --shell /bin/bash --create-home zensensei

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
# The build context is the repo root (zensensei-backend/) so that
# both the shared library and the service source are available.
COPY shared/ ./shared/
COPY services/integration_service/ ./integration_service/

# Create credentials directory (mounted as secret in production)
RUN mkdir -p /app/credentials && chown -R zensensei:zensensei /app

# Switch to non-root user
USER zensensei

# ── Environment defaults ────────────────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PORT=8004 \
    WORKERS=2 \
    ENVIRONMENT=production

EXPOSE 8004

# ── Health check ──────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/health')" \
    || exit 1

# ── Entrypoint ─────────────────────────────────────────────────────────────────
# Use sh -c so the shell expands ${PORT:-8004} at container start time.
# Railway injects PORT; the :-8004 fallback keeps local Docker working.
CMD ["sh", "-c", \
    "uvicorn integration_service.main:app \
    --host 0.0.0.0 \
    --port ${PORT:-8004} \
    --workers ${WORKERS:-2} \
    --log-level info \
    --no-access-log \
    --proxy-headers \
    --forwarded-allow-ips='*'" \
]
