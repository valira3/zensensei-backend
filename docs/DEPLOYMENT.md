# Deployment Guide

## Google Cloud Run

### Prerequisites

- GCP project with billing enabled
- Docker installed
- gcloud CLI configured
- Neo4j AuraDB instance
- Redis instance (Cloud Memorystore or similar)

### Steps

1. Build and push Docker images to GCR:
```bash
make build
docker push gcr.io/PROJECT_ID/SERVICE_NAME:latest
```

2. Deploy each service to Cloud Run:
```bash
make deploy-dev
```

3. Set environment variables in Cloud Run:
```bash
gcloud run services update SERVICE_NAME --set-env-vars KEY=VALUE
```

### CI/CD

The GitHub Actions workflow in `.github/workflows/ci.yml` handles:
1. Lint and format checks
2. Unit tests
3. Security scanning
4. Docker build and push to GCR
5. Deploy to Cloud Run on merge to main

## Local Development

See `docs/GETTING_STARTED.md` for local setup instructions.
