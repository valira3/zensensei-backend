# ─── Stage 1: Builder ─────────────────────────────────────────────────────────
# Installs all dependencies into a virtual environment so only the compiled
# wheels and the venv are copied to the final stage (no build tooling ships).
FROM python:3.11-slim AS builder

# Build-time dependencies for packages that compile C extensions (e.g. bcrypt)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Create a virtual environment to isolate dependencies
ENV VIRTUAL_ENV=/opt/venv
RUN python -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Copy and install requirements first (layer-cached until requirements change)
COPY requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r /tmp/requirements.txt


# ─── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Security: run as a non-root user
RUN groupadd --gid 1001 appgroup \
    && useradd  --uid 1001 --gid 1001 --no-create-home --shell /bin/false appuser

# Runtime OS dependencies (e.g. libssl for TLS, libffi for cffi-backed libs)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libssl3 \
        libffi8 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy the virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV VIRTUAL_ENV=/opt/venv

# Working directory
WORKDIR /app

# Copy the shared library (required by all services)
COPY shared/ ./shared/

# Copy only the user service source
COPY services/user_service/ ./services/user_service/

# ── Python path ────────────────────────────────────────────────────────────
# Make both the monorepo root (/app) and the services directory importable
# so that `from shared.X import ...` and `from services.user_service.X import ...`
# work without editable installs.
ENV PYTHONPATH="/app:/app/services"

# ── Runtime configuration ────────────────────────────────────────────────────
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Default port — override via USER_SERVICE_PORT env var
    PORT=8001

# Health check using the /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f "http://localhost:${PORT}/health" || exit 1

# Drop to non-root user
USER appuser

EXPOSE 8001

# Launch with uvicorn; the number of workers is controlled by the orchestrator
# via the WEB_CONCURRENCY env variable (gunicorn-compatible convention).
CMD ["sh", "-c", \
    "uvicorn services.user_service.main:app \
        --host 0.0.0.0 \
        --port ${PORT:-8001} \
        --workers ${WEB_CONCURRENCY:-1} \
        --log-level info \
        --no-access-log"]
