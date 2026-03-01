FROM python:3.12-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ ./shared/
COPY gateway/ ./gateway/

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
USER appuser

ENV PORT=4000
EXPOSE 4000

HEALTHCHECK --interval=15s --timeout=10s --retries=3 --start-period=20s \
    CMD curl -f http://localhost:${PORT}/health || exit 1

CMD ["sh", "-c", \
     "python -m uvicorn gateway.main:app \
          --host 0.0.0.0 \
          --port ${PORT:-4000} \
          --workers ${WEB_CONCURRENCY:-2} \
          --log-config /dev/null"]
