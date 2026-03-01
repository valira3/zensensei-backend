# ZenSensei AI Reasoning Service -- Dockerfile
# Multi-stage build

FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential gcc libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

RUN python -m venv /build/venv
ENV PATH="/build/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim AS runtime

RUN groupadd --gid 1001 zensensei && \
    useradd --uid 1001 --gid zensensei --shell /bin/bash --create-home zensensei

WORKDIR /app

COPY --from=builder /build/venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

COPY shared/ ./shared/
COPY services/ai_reasoning_service/ ./services/ai_reasoning_service/

ENV PYTHONPATH="/app:$PYTHONPATH"
ENV ENVIRONMENT=production \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8003

EXPOSE 8003

USER zensensei

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:' + __import__('os').environ.get('PORT','8003') + '/health')"

CMD ["sh", "-c", \
     "uvicorn services.ai_reasoning_service.main:app \
          --host 0.0.0.0 \
          --port ${PORT:-8003} \
          --workers ${WEB_CONCURRENCY:-2} \
          --log-level info"]
