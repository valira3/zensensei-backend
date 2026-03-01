# ZenSensei Backend

> AI-powered personal intelligence platform — Railway-ready microservices

[![CI](https://github.com/valira3/zensensei-backend/actions/workflows/ci.yml/badge.svg)](https://github.com/valira3/zensensei-backend/actions/workflows/ci.yml)
[![Security](https://github.com/valira3/zensensei-backend/actions/workflows/security.yml/badge.svg)](https://github.com/valira3/zensensei-backend/actions/workflows/security.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104%2B-green)](https://fastapi.tiangolo.com/)
[![Railway](https://img.shields.io/badge/Deploy-Railway-blueviolet)](https://railway.app/)

---

## Overview

ZenSensei is an AI-powered life coach and personal knowledge graph platform. This repository contains the complete backend — a suite of FastAPI microservices deployable to Railway in minutes.

### Architecture

```
┌───────────────┐
│  API Gateway  │  ← Public entry point (port 4000)
└─────┬─────┘
          │ routes to…
  ┌──────┴──────────────────────────────────────────────────┐
  │                                                  │
┌─┴──────┐ ┌───────────┐ ┌───────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│  User    │ │   Graph    │ │    AI      │ │ Integr-  │ │ Notific- │ │Analytics │
│ Service  │ │  Query    │ │ Reasoning │ │ ation    │ │ ation    │ │ Service  │
│ :8001    │ │ Service  │ │ Service   │ │ Service  │ │ Service  │ │ :8006    │
└────────┘ └───────────┘ └───────────┘ └──────────┘ └──────────┘ └──────────┘
                                        │
                          ┌─────────┴─────────┐
                    ┌────┴────┐       ┌────┴────┐
                    │  Neo4j  │       │  Redis  │
                    └────────┘       └────────┘
```

### Services

| Service | Port | Responsibility |
|---|---|---|
| **API Gateway** | 4000 | JWT auth, routing, rate limiting, health aggregation |
| **User Service** | 8001 | Auth, registration, profiles, onboarding |
| **Graph Query Service** | 8002 | Neo4j knowledge graph CRUD and traversal |
| **AI Reasoning Service** | 8003 | Gemini-powered insights, decisions, recommendations |
| **Integration Service** | 8004 | OAuth connectors (Google Calendar, Gmail, Notion, Plaid, Spotify) |
| **Notification Service** | 8005 | Push, email, in-app notifications via SendGrid |
| **Analytics Service** | 8006 | Event tracking, metrics, pattern detection, reports |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- A Neo4j instance (local or [Neo4j AuraDB](https://neo4j.com/cloud/aura/) free tier)
- A Redis instance (local or [Railway Redis](https://railway.app/))

### 1. Clone & configure

```bash
git clone https://github.com/valira3/zensensei-backend.git
cd zensensei-backend
cp .env.example .env
# Edit .env with your credentials
```

### 2. Run locally with Docker Compose

```bash
make dev          # Start all services
make seed         # Load sample data
make test         # Run test suite
```

Visit `http://localhost:4000/docs` for the unified Swagger UI.

### 3. Deploy to Railway

```bash
bash scripts/deploy-railway.sh production
```

See [docs/RAILWAY_DEPLOYMENT.md](docs/RAILWAY_DEPLOYMENT.md) for the full guide.

---

## Project Structure

```
zensensei-backend/
├── gateway/                # API Gateway service
├── services/
│   ├── user_service/
│   ├── graph_query_service/
│   ├── ai_reasoning_service/
│   ├── integration_service/
│   ├── notification_service/
│   └── analytics_service/
├── shared/                 # Shared models, DB clients, middleware
├── scripts/                # Deploy, seed, migration scripts
├── data/                   # Sample / seed data JSON
├── docs/                   # Extended documentation
├── railway-configs/        # Per-service Railway TOML overrides
├── terraform/              # (Optional) GCP IaC
├── docker-compose.yml
├── railway.json
├── railway.toml
├── Procfile
├── requirements.txt
└── Makefile
```

---

## Documentation

| Doc | Description |
|---|---|
| [Getting Started](docs/GETTING_STARTED.md) | Local dev setup walkthrough |
| [API Reference](docs/API.md) | Full endpoint catalogue |
| [Architecture](docs/ARCHITECTURE.md) | System design & data flow |
| [Railway Deployment](docs/RAILWAY_DEPLOYMENT.md) | Step-by-step Railway guide |
| [General Deployment](docs/DEPLOYMENT.md) | Docker & GCP deployment |

---

## Environment Variables

See [`.env.example`](.env.example) and [railway-env-vars.md](railway-env-vars.md) for the complete reference.

Minimum required variables:

```env
SECRET_KEY=          # Random 64-char hex string
NEO4J_URI=           # bolt:// or neo4j+s:// URI
NEO4J_USER=          # Neo4j username
NEO4J_PASSWORD=      # Neo4j password
REDIS_HOST=          # Redis hostname
FIREBASE_PROJECT_ID= # GCP project ID
```

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Commit with conventional commits: `git commit -m "feat: add my feature"`
4. Push & open a PR

All PRs must pass CI (lint, tests, security scan) before merging.

---

## License

MIT © 2026 ZenSensei
