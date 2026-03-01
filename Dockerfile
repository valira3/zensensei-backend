# ─── Root Dockerfile ──────────────────────────────────────────────────────────
# Default service: API Gateway
# Railway uses this when no dockerfilePath is specified.
# For individual microservice Dockerfiles, see:
#   gateway/Dockerfile, services/*/Dockerfile, frontend/Dockerfile
# ──────────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim

# ── System deps ───────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ── Working directory ─────────────────────────────────────────────────────────
WORKDIR /app

# ── Python deps ───────────────────────────────────────────────────────────────
COPY gateway/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# ── Application code ──────────────────────────────────────────────────────────
COPY gateway/ ./

# ── Runtime ───────────────────────────────────────────────────────────────────
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
