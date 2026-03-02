# ─── Root Dockerfile ─────────────────────────────────────────────────────────
# Default service: API Gateway
# Railway uses this when no dockerfilePath is specified.
# For individual microservice Dockerfiles, see:
#   gateway/Dockerfile, services/*/Dockerfile, frontend/Dockerfile
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim

# ── System deps ───────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ── Working directory ──────────────────────────────────────────────────────
WORKDIR /app

# ── Install Python dependencies ────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy shared library and gateway source ─────────────────────────────────
COPY shared/ ./shared/
COPY gateway/ ./gateway/

# ── Python path ────────────────────────────────────────────────────────────
ENV PYTHONPATH="/app"

# ── Non-root user ──────────────────────────────────────────────────────────
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
USER appuser

# ── Default port (Railway overrides via $PORT) ─────────────────────────────
ENV PORT=4000

EXPOSE 4000

# ── Health check ───────────────────────────────────────────────────────────
HEALTHCHECK --interval=15s --timeout=10s --retries=3 --start-period=20s \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# ── Start ──────────────────────────────────────────────────────────────────
CMD ["sh", "-c", \
     "python -m uvicorn gateway.main:app \
          --host 0.0.0.0 \
          --port ${PORT:-4000} \
          --workers ${WEB_CONCURRENCY:-2} \
          --log-level info"]
