# ZenSensei Backend

> AI-powered personal intelligence platform — graph-native microservices backend

[![CI/CD](https://github.com/zensensei/zensensei-backend/actions/workflows/ci.yml/badge.svg)](https://github.com/zensensei/zensensei-backend/actions/workflows/ci.yml)
[![Security](https://github.com/zensensei/zensensei-backend/actions/workflows/security.yml/badge.svg)](https://github.com/zensensei/zensensei-backend/actions/workflows/security.yml)
[![codecov](https://codecov.io/gh/zensensei/zensensei-backend/graph/badge.svg)](https://codecov.io/gh/zensensei/zensensei-backend)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Security Policy](https://img.shields.io/badge/Security-Policy-red.svg)](SECURITY.md)

---

## What is ZenSensei?

ZenSensei is an AI-powered personal intelligence platform that maps the connections between your goals, habits, relationships, tasks, and life events in a knowledge graph. It uses this graph structure, powered by Neo4j, to generate AI insights that surface patterns and opportunities invisible to traditional linear to-do apps.

The backend is a Python (FastAPI) monorepo of seven microservices deployed to Google Cloud Run, with Neo4j as the core data model, Redis for caching, and Pub/Sub for event-driven service coordination.

---

## Architecture Overview

```
                    ┌─────────────────────────────────────────┐
                    │           API GATEWAY  :4000             │
                    └──┬──────┬──────┬──────┬──────┬──────┬──┘
                       │      │      │      │      │      │
         ┌─────────────┘      │      │      │      │      └──────────────┐
         ▼                    ▼      ▼      ▼      ▼                    ▼
  ┌──────────────┐   ┌──────────────┐ ┌──────────────┐  ┌──────────────────┐
  │ USER SERVICE │   │ GRAPH QUERY  │ │ AI REASONING │  │  INTEGRATION     │
  │    :8001     │   │   SERVICE    │ │   SERVICE    │  │    SERVICE       │
  │              │   │    :8002     │ │    :8003     │  │     :8004        │
  └──────────────┘   └──────┬───────┘ └──────────────┘  └──────────────────┘
                            │
              ┌─────────────┴──────────────┐
              ▼                            ▼
        ┌───────────┐              ┌──────────────┐
        │  Neo4j    │              │    Redis     │
        │  Graph DB │              │    Cache     │
        └───────────┘              └──────────────┘

  ┌──────────────────┐  ┌──────────────────────────────────────┐
  │ NOTIFICATION SVC │  │         Google Pub/Sub               │
  │     :8005        │  │  user-events  graph-updates  ai-jobs │
  └──────────────────┘  └──────────────────────────────────────┘
  ┌──────────────────┐
  │  ANALYTICS SVC   │
  │     :8006        │
  └──────────────────┘
```

For the full architecture documentation including data flow diagrams, technology decisions, and security model, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Quick Start

### Prerequisites

- **Python 3.12+** — [download](https://www.python.org/downloads/)
- **Docker Desktop** — [download](https://www.docker.com/products/docker-desktop/)
- **Redis** — provided via Docker (no separate install needed for local dev)
- **Make** — pre-installed on macOS/Linux; on Windows use WSL2 or [GnuWin32](http://gnuwin32.sourceforge.net/packages/make.htm)

```bash
git clone https://github.com/zensensei/zensensei-backend.git
cd zensensei-backend

cp .env.example .env           # Configure environment
make setup                     # Install Python dependencies
make dev                       # Start all services
make seed                      # Load sample data

curl http://localhost:4000/health  # Verify gateway is up
```

The full stack will be available at:
- **API Gateway:** http://localhost:4000
- **Neo4j Browser:** http://localhost:7474

For a step-by-step guide including API exploration and troubleshooting, see [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md).

---

## Service Map

| Service | Local Port | Description |
|---------|-----------|-------------|
| **API Gateway** | 4000 | Entry point — routes all client traffic, JWT validation, rate limiting |
| **User Service** | 8001 | Registration, login, profiles, preferences, sessions |
| **Graph Query Service** | 8002 | Neo4j CRUD, Cypher queries, Redis cache, graph algorithms |
| **AI Reasoning Service** | 8003 | Insight generation, decision analysis, recommendations (Gemini) |
| **Integration Service** | 8004 | OAuth flows, data sync, webhooks for 67+ external services |
| **Notification Service** | 8005 | Push notifications, email, in-app messages |
| **Analytics Service** | 8006 | Goal tracking, habit metrics, GDPR data exports |
| Neo4j | 7474 / 7687 | Graph database (infrastructure) |
| Redis | 6379 | Cache + session store (infrastructure) |
| Firestore Emulator | 8080 | Firestore local emulator (infrastructure) |

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **Framework** | FastAPI + Python 3.11 | Async-native, auto OpenAPI docs, Pydantic v2 validation |
| **Graph DB** | Neo4j 5.14 | Property graph for life data — multi-hop traversal, Cypher queries |
| **Document DB** | Firestore | Serverless scaling for user records and settings |
| **Cache** | Redis 7 | Query caching, rate limiting, session state |
| **AI** | Google Gemini (+ Claude fallback) | Native GCP integration, multimodal, provider-agnostic SDK |
| **Event bus** | Google Cloud Pub/Sub | Async decoupling between services with guaranteed delivery |
| **Infra** | Terraform 1.7 on GCP | IaC — GKE, Cloud Run, VPC, Monitoring |
| **CI/CD** | GitHub Actions | Lint → test → build → deploy on push to main |
| **Containers** | Docker + Cloud Run | Per-request billing, scale-to-zero in staging |
| **Orchestration** | GKE Autopilot | Neo4j stateful workload (managed nodes) |

---

## Development Workflow

```bash
# Daily development
make dev            # Start full Docker stack
make test           # Run tests (requires stack running)
make lint           # Run ruff + black + mypy

# Before opening a PR
make lint           # Must pass
make test           # Must pass with >= 80% coverage

# Dependency management
pip install <package>
pip freeze > requirements.txt
# or: use pip-compile for deterministic pinning

# Cleaning up
make clean          # Stop containers, remove volumes
```

### Code Style

- **Formatter:** `black` (line length 100)
- **Linter:** `ruff` (replaces flake8 + isort + pylint)
- **Type checker:** `mypy` (strict mode on `shared/`)
- **Pre-commit hooks:** Run `pre-commit install` to enforce lint on every commit

---

## Project Structure

```
zensensei-backend/
├── .github/
│   └── workflows/
│       ├── ci.yml              # Main pipeline: lint → test → build → deploy
│       └── security.yml        # Security scans: bandit, trivy, gitleaks, codeql
│
├── services/
│   ├── user_service/           # :8001 — auth, profiles, sessions
│   ├── graph_query_service/    # :8002 — Neo4j, Redis cache
│   ├── ai_reasoning_service/   # :8003 — Gemini, insights, decisions
│   ├── integration_service/    # :8004 — OAuth, sync, webhooks
│   ├── notification_service/   # :8005 — push, email, in-app
│   ├── analytics_service/      # :8006 — metrics, exports
│   └── api_gateway/            # :4000 — routing, auth, rate limiting
│
├── shared/                     # Shared library (imported by all services)
│   ├── auth.py                 # JWT utilities, auth dependencies
│   ├── config.py               # Pydantic settings with env var support
│   ├── database/               # Neo4j, Firestore, Redis clients
│   ├── events/                 # Pub/Sub publisher/subscriber
│   ├── middleware/             # CORS, logging, rate limit, error handler
│   └── models/                 # Shared Pydantic models
│
├── terraform/                  # Infrastructure as Code
│   ├── main.tf                 # Root config — modules + provider
│   ├── variables.tf            # All input variables
│   ├── outputs.tf              # Service URLs, database endpoints
│   ├── modules/
│   │   ├── vpc/                # VPC, subnets, NAT, VPC connector
│   │   ├── gke/                # GKE Autopilot for Neo4j
│   │   ├── cloud_run/          # All 7 Cloud Run services + IAM
│   │   ├── storage/            # GCS buckets (media, backups, exports)
│   │   ├── pubsub/             # Topics + subscriptions
│   │   └── monitoring/         # Dashboards + alert policies
│   └── environments/
│       ├── production/         # Production tfvars
│       └── staging/            # Staging tfvars
│
├── docs/
│   ├── API.md                  # Full API reference with examples
│   ├── ARCHITECTURE.md         # System design and data flow
│   ├── GETTING_STARTED.md      # Local development guide
│   └── DEPLOYMENT.md           # GCP deployment guide
│
├── tests/                      # Test suite
├── docker-compose.yml          # Full local stack
├── Makefile                    # Developer convenience commands
├── pyproject.toml              # Python tooling config (ruff, black, mypy)
├── requirements.txt            # Production dependencies
└── requirements-dev.txt        # Development + test dependencies
```

---

## Deployment

ZenSensei deploys to Google Cloud Platform using Terraform (infrastructure) and GitHub Actions (application).

**Quick deploy to staging:**
```bash
make deploy-staging
```

**Full deployment flow:**
1. Push to `main` triggers GitHub Actions CI pipeline
2. `lint` → `test` jobs must pass
3. `build` job builds and pushes 7 Docker images to GCR (parallel)
4. `deploy` job deploys each service to Cloud Run (parallel)
5. Health check verification before traffic shift

For initial GCP project setup and Terraform configuration, see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

---

## Deploy on Railway

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/template/zensensei-backend)

Railway is a simpler alternative to GCP for teams that want the full microservices stack without Terraform or Kubernetes. The entire ZenSensei backend (7 services + Redis) deploys as a single Railway project.

**One-click deploy:** Click the badge above, or follow the guide below.

**Quick CLI deploy:**
```bash
npm install -g @railway/cli
railway login
./scripts/deploy-railway.sh setup   # Create project + all services + Redis
./scripts/deploy-railway.sh deploy  # Deploy everything
./scripts/deploy-railway.sh status  # Check deployment status
```

**Service → Railway mapping:**

| Service | Dockerfile | Railway Internal URL |
|---|---|---|
| API Gateway | `gateway/Dockerfile` | *(public domain — only externally accessible)* |
| User Service | `services/user_service/Dockerfile` | `http://user-service.railway.internal:8001` |
| Graph Query | `services/graph_query_service/Dockerfile` | `http://graph-query-service.railway.internal:8002` |
| AI Reasoning | `services/ai_reasoning_service/Dockerfile` | `http://ai-reasoning-service.railway.internal:8003` |
| Integration | `services/integration_service/Dockerfile` | `http://integration-service.railway.internal:8004` |
| Notification | `services/notification_service/Dockerfile` | `http://notification-service.railway.internal:8005` |
| Analytics | `services/analytics_service/Dockerfile` | `http://analytics-service.railway.internal:8006` |
| Redis | Railway managed plugin | `${{Redis.REDIS_URL}}` |

**Key configuration files:**
- [`railway.toml`](railway.toml) — Project-level build and deploy settings
- [`railway.json`](railway.json) — Multi-service template definition
- [`railway-configs/`](railway-configs/) — Per-service Dockerfile and env var reference
- [`railway-env-vars.md`](railway-env-vars.md) — Complete environment variable reference

For the full step-by-step guide including database setup, networking, scaling, and troubleshooting, see [docs/RAILWAY_DEPLOYMENT.md](docs/RAILWAY_DEPLOYMENT.md).

---

## API Documentation

The full API reference is in [docs/API.md](docs/API.md), covering all endpoints across all seven services with request/response examples.

In local development, each service exposes interactive Swagger UI:
- Gateway: http://localhost:4000/docs
- User Service: http://localhost:8001/docs
- Graph Query: http://localhost:8002/docs
- AI Reasoning: http://localhost:8003/docs

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make changes following the code style guidelines
4. Ensure tests pass: `make test`
5. Ensure linters pass: `make lint`
6. Write or update tests for any changed behavior
7. Commit with a descriptive message following [Conventional Commits](https://www.conventionalcommits.org/)
8. Open a pull request to `develop`

### Commit conventions

```
feat(user-service): add OAuth Google login
fix(graph-query): handle disconnected Neo4j gracefully  
docs(api): add missing response examples for /insights
test(ai-reasoning): add unit tests for insight scoring
chore(deps): bump fastapi from 0.110.0 to 0.111.0
```

### Pull request guidelines

- PRs to `develop` require at least one reviewer approval
- PRs to `main` require two reviewer approvals + passing CI
- Keep PRs focused — one feature or fix per PR
- Include test coverage for new code
- Update `docs/API.md` for any endpoint changes

---

## Security

To report a security vulnerability, email **security@zensensei.net**. Please do not open a public GitHub issue. See [SECURITY.md](SECURITY.md) for the full security policy.

---

## License

MIT — see [LICENSE](LICENSE) for details.
