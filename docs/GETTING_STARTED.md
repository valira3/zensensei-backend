# Getting Started with ZenSensei Backend

This guide walks you from zero to a fully running local development environment in under 10 minutes.

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11+ | [python.org](https://python.org) or `pyenv install 3.11` |
| Docker Desktop | 24+ | [docker.com/get-started](https://docker.com/get-started) |
| Docker Compose | v2.20+ | Included with Docker Desktop |
| Git | 2.40+ | `brew install git` / package manager |
| Make | 3.81+ | Included on macOS/Linux |

**Optional (for cloud workflows):**
- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) (`gcloud`) — for GCP integration and deployment
- [Terraform](https://developer.hashicorp.com/terraform/install) 1.7+ — for infrastructure management

---

## 1. Clone the Repository

```bash
git clone https://github.com/zensensei/zensensei-backend.git
cd zensensei-backend
```

---

## 2. Configure Environment Variables

Copy the example environment file and fill in required values:

```bash
cp .env.example .env
```

Open `.env` and set the required values:

```bash
# Required — generate a strong secret key
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
echo "SECRET_KEY=$SECRET_KEY" >> .env

# Optional — only needed for AI features
# GEMINI_API_KEY=your-gemini-api-key-here
# ANTHROPIC_API_KEY=your-anthropic-api-key-here
```

For local development, the infrastructure services (Neo4j, Redis, Firestore emulator) are pre-configured with defaults in `.env.example`. You only need a real Gemini API key if you want to test AI insight generation.

---

## 3. Install Python Dependencies

```bash
make setup
```

This creates a virtual environment at `.venv/` and installs all production and development dependencies.

Alternatively, manually:
```bash
python3.11 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
```

---

## 4. Start All Services with Docker Compose

```bash
make dev
```

This starts the full stack:

```
Starting infrastructure:
  ✓ Neo4j         → http://localhost:7474  (browser UI)
  ✓ Redis         → localhost:6379
  ✓ Firestore     → localhost:8080

Starting microservices:
  ✓ User Service          → http://localhost:8001
  ✓ Graph Query Service   → http://localhost:8002
  ✓ AI Reasoning Service  → http://localhost:8003
  ✓ Integration Service   → http://localhost:8004
  ✓ Notification Service  → http://localhost:8005
  ✓ Analytics Service     → http://localhost:8006
  ✓ API Gateway           → http://localhost:4000
```

Wait for all health checks to pass (approximately 45–60 seconds on first run while Docker pulls images).

**Verify everything is running:**
```bash
curl http://localhost:4000/health
# → {"status": "healthy", "service": "gateway", ...}
```

---

## 5. Seed Sample Data

Populate the graph with sample users, goals, habits, and relationships:

```bash
make seed
```

This creates:
- 3 sample user accounts (credentials printed to console)
- A rich knowledge graph per user (goals, tasks, habits, relationships)
- Sample integration data

Sample user credentials after seeding:
```
Email:    demo@zensensei.app
Password: Demo!Zensensei2026
```

---

## 6. Run Individual Services

You can run a single service without Docker Compose for faster development iteration:

```bash
# Activate virtual environment first
source .venv/bin/activate

# Start just the User Service
uvicorn services.user_service.main:app --reload --port 8001

# Start just the Graph Query Service
uvicorn services.graph_query_service.main:app --reload --port 8002

# Start just the AI Reasoning Service
uvicorn services.ai_reasoning_service.main:app --reload --port 8003
```

The services still require Neo4j, Redis, and the Firestore emulator — start them first:

```bash
docker compose up neo4j redis firestore-emulator -d
```

---

## 7. Explore the API with Swagger UI

Each service exposes an interactive Swagger UI in development mode:

| Service | Swagger URL |
|---------|-------------|
| User Service | http://localhost:8001/docs |
| Graph Query Service | http://localhost:8002/docs |
| AI Reasoning Service | http://localhost:8003/docs |
| Integration Service | http://localhost:8004/docs |
| Notification Service | http://localhost:8005/docs |
| Analytics Service | http://localhost:8006/docs |

**Quick API test with the seeded demo user:**

```bash
# 1. Get a token
TOKEN=$(curl -s -X POST http://localhost:8001/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@zensensei.app","password":"Demo!Zensensei2026"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")

# 2. Get user profile
curl -H "Authorization: Bearer $TOKEN" http://localhost:8001/api/v1/auth/me

# 3. List graph nodes
curl -H "Authorization: Bearer $TOKEN" http://localhost:8002/api/v1/nodes
```

---

## 8. Run Tests

```bash
make test
pytest tests/services/user_service/ -v
pytest tests/ --cov=services --cov=shared --cov-report=html
```

---

## Common Issues

**Neo4j takes too long to start:** First boot can take 60–90 seconds. Run `docker compose logs neo4j` to monitor.

**Port already in use:** Check `lsof -i :8001`. Stop conflicting processes or change ports in `.env`.

**`ModuleNotFoundError: No module named 'shared'`:** Run from repo root with virtualenv activated: `source .venv/bin/activate`.

**AI endpoints return empty insights:** Set a valid `GEMINI_API_KEY` in `.env`.

**Firestore emulator not available:** Services fall back to in-memory storage. This is expected behavior in minimal local setups.
