# Railway Deployment Guide — ZenSensei Backend

> Deploy the full ZenSensei microservices stack to Railway.app.
> This guide covers both the dashboard (point-and-click) and CLI (scriptable) approaches.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Architecture on Railway](#2-architecture-on-railway)
3. [Quick Start — Dashboard](#3-quick-start--dashboard)
4. [Quick Start — CLI](#4-quick-start--cli)
5. [Service Configuration Reference](#5-service-configuration-reference)
6. [Database Setup](#6-database-setup)
7. [Networking](#7-networking)
8. [Environment Variables](#8-environment-variables)
9. [Monitoring & Logs](#9-monitoring--logs)
10. [Scaling](#10-scaling)
11. [Troubleshooting](#11-troubleshooting)
12. [Cost Estimate](#12-cost-estimate)

---

## 1. Prerequisites

### Accounts & Tools

| Tool | Purpose | Install |
|---|---|---|
| Railway account | Cloud platform | [railway.app](https://railway.app) |
| Railway CLI | Command-line deploy | `npm i -g @railway/cli` or [docs](https://docs.railway.app/develop/cli) |
| GitHub account | Source code hosting | — |
| Docker Desktop | Local build verification | [docker.com](https://www.docker.com/products/docker-desktop/) |

### Verify Railway CLI

```bash
railway --version   # Should print e.g. railway 3.x.x
railway login       # Opens browser for OAuth — complete login
railway whoami      # Should print your account email
```

### Fork / Push the Repo

Railway deploys from GitHub. Ensure your fork is pushed to GitHub before proceeding:

```bash
git remote -v          # Verify origin points to your GitHub repo
git push origin main   # Push latest code
```

---

## 2. Architecture on Railway

ZenSensei maps to **one Railway project** containing **nine services** (7 backend + 1 frontend + 1 Redis plugin):

```
Railway Project: zensensei-backend
│
├── gateway          (API Gateway — Python/FastAPI, port 8000)
├── auth             (Auth Service — Python/FastAPI, port 8001)
├── journal          (Journal Service — Python/FastAPI, port 8002)
├── mood             (Mood Service — Python/FastAPI, port 8003)
├── breathing        (Breathing Service — Python/FastAPI, port 8004)
├── insights         (Insights Service — Python/FastAPI, port 8005)
├── notifications    (Notifications Service — Python/FastAPI, port 8006)
├── integrations     (Integrations Service — Python/FastAPI, port 8007)
├── frontend         (Static Web App — nginx, port 80)
└── Redis            (Railway Redis plugin)
```

### Public vs Private Endpoints

| Service | Public URL | Notes |
|---|---|---|
| `gateway` | `https://gateway-xxxx.up.railway.app` | Single public entry point |
| `frontend` | `https://frontend-xxxx.up.railway.app` | Serves static HTML/CSS/JS |
| All others | Internal only | Referenced via `${{service.RAILWAY_PRIVATE_DOMAIN}}` |

---

## 3. Quick Start — Dashboard

### Step 1 — Create Project

1. Go to [railway.app/new](https://railway.app/new)
2. Click **"Deploy from GitHub repo"**
3. Authorize Railway and select `zensensei-backend`
4. Railway auto-detects the root `Dockerfile` and creates a **gateway** service

### Step 2 — Add Backend Services

For each microservice, click **"+ New Service" → "GitHub Repo"** and set:

| Service | Dockerfile Path | Root Directory |
|---|---|---|
| `auth` | `services/auth/Dockerfile` | *(leave blank)* |
| `journal` | `services/journal/Dockerfile` | *(leave blank)* |
| `mood` | `services/mood/Dockerfile` | *(leave blank)* |
| `breathing` | `services/breathing/Dockerfile` | *(leave blank)* |
| `insights` | `services/insights/Dockerfile` | *(leave blank)* |
| `notifications` | `services/notifications/Dockerfile` | *(leave blank)* |
| `integrations` | `services/integrations/Dockerfile` | *(leave blank)* |

### Step 3 — Add Frontend Service

1. Click **"+ New Service" → "GitHub Repo"**
2. Name it `frontend`
3. Set **Dockerfile Path** to `frontend/Dockerfile`
4. Leave Root Directory blank (build context is the repo root)
5. No environment variables needed — nginx serves static files
6. Railway will assign a public URL automatically

### Step 4 — Add Redis

1. Click **"+ New" → "Database" → "Redis"**
2. Railway provisions Redis and injects `REDIS_URL` automatically

### Step 5 — Add Databases

For each service that needs Postgres, click **"+ New" → "Database" → "PostgreSQL"**.

### Step 6 — Set Environment Variables

Set variables on each service (see [Section 8](#8-environment-variables) for the full list).

---

## 4. Quick Start — CLI

```bash
# 1. Login and link project
railway login
railway link   # Select or create your project

# 2. Deploy gateway (uses root Dockerfile by default)
railway up --service gateway

# 3. Deploy each microservice
for svc in auth journal mood breathing insights notifications integrations; do
  railway up --service $svc --dockerfile services/$svc/Dockerfile
done

# 4. Deploy frontend
railway up --service frontend --dockerfile frontend/Dockerfile

# 5. Check status
railway status
railway logs --service gateway
```

---

## 5. Service Configuration Reference

Each service has a corresponding config file in `railway-configs/`:

| File | Used by |
|---|---|
| `railway.toml` | Default (gateway) |
| `railway.json` | All services — multi-service schema |
| `railway-configs/frontend.toml` | Frontend nginx service |

### Frontend Service Settings

```toml
# railway-configs/frontend.toml
[build]
dockerfilePath = "frontend/Dockerfile"

[deploy]
healthcheckPath = "/health"
healthcheckTimeout = 30
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 3
```

The frontend service:
- Builds from `frontend/Dockerfile` using the **repo root** as build context
- Copies `frontend/public/` static files into nginx
- Exposes port **80** internally; Railway maps to HTTPS automatically
- Health check hits `GET /health` which returns `200 ok`

---

## 6. Database Setup

### Provision Databases

```
Auth Service     → AUTH_DATABASE_URL
Journal Service  → JOURNAL_DATABASE_URL
Mood Service     → MOOD_DATABASE_URL
Insights Service → INSIGHTS_DATABASE_URL
Notifications    → NOTIFICATIONS_DATABASE_URL
Integrations     → INTEGRATIONS_DATABASE_URL
```

### Run Migrations

```bash
railway run --service auth python manage.py migrate
railway run --service journal python manage.py migrate
# ... repeat for each service
```

---

## 7. Networking

### Private Networking (service-to-service)

Railway services on the same project communicate via private networking:

```
gateway → http://auth.railway.internal:8001
gateway → http://journal.railway.internal:8002
gateway → http://mood.railway.internal:8003
... etc
```

Use Railway reference variables in your environment config:

```
AUTH_SERVICE_URL=${{auth.RAILWAY_PRIVATE_DOMAIN}}
JOURNAL_SERVICE_URL=${{journal.RAILWAY_PRIVATE_DOMAIN}}
```

### Custom Domains

1. Go to **Service Settings → Domains**
2. Click **"+ Custom Domain"**
3. Add your domain and follow DNS instructions
4. Railway provisions TLS automatically

---

## 8. Environment Variables

### Shared (all backend services)

| Variable | Description | Example |
|---|---|---|
| `JWT_SECRET` | JWT signing secret | `openssl rand -hex 32` |
| `REDIS_URL` | Redis connection string | Auto-injected by Railway |
| `LOG_LEVEL` | Logging verbosity | `info` |

### Gateway Service

| Variable | Description |
|---|---|
| `AUTH_SERVICE_URL` | Internal URL for auth service |
| `JOURNAL_SERVICE_URL` | Internal URL for journal service |
| `MOOD_SERVICE_URL` | Internal URL for mood service |
| `BREATHING_SERVICE_URL` | Internal URL for breathing service |
| `INSIGHTS_SERVICE_URL` | Internal URL for insights service |
| `NOTIFICATIONS_SERVICE_URL` | Internal URL for notifications service |
| `INTEGRATIONS_SERVICE_URL` | Internal URL for integrations service |

### Insights Service

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI API key for AI insights |
| `INSIGHTS_DATABASE_URL` | Postgres connection string |

### Frontend Service

No environment variables required. nginx serves static files directly.

Optional: If you need to inject the API gateway URL at build time, add:

```
VITE_API_URL=https://your-gateway.up.railway.app
```

---

## 9. Monitoring & Logs

### View Logs

```bash
railway logs --service gateway --tail 100
railway logs --service frontend --tail 50
```

### Health Endpoints

| Service | Health URL |
|---|---|
| Gateway | `GET /health` |
| All microservices | `GET /health` |
| Frontend (nginx) | `GET /health` → returns `200 ok` |

---

## 10. Scaling

```bash
# Scale a service to 2 replicas
railway scale --service gateway --replicas 2
```

For the frontend service, Railway's CDN-like edge caching handles most traffic — scaling is rarely needed for static sites.

---

## 11. Troubleshooting

### Frontend build fails

```
Error: COPY failed: file not found: frontend/public/
```

**Fix:** Ensure the build context is the **repo root**, not the `frontend/` subdirectory. The `frontend/Dockerfile` uses `COPY frontend/public/ /usr/share/nginx/html/`.

### Health check fails on frontend

Verify `frontend/nginx.conf` contains:
```nginx
location /health {
    access_log off;
    return 200 'ok';
    add_header Content-Type text/plain;
}
```

### Services can't reach each other

- Verify all services are in the **same Railway project**
- Use `${{service.RAILWAY_PRIVATE_DOMAIN}}` reference variables, not hardcoded URLs
- Check that Railway private networking is enabled (it's on by default)

### Viewing deployment history

```bash
railway deployments --service gateway
```

---

## 12. Cost Estimate

| Resource | Estimate |
|---|---|
| 8 compute services (gateway + 6 microservices + frontend) | ~$5–20/mo |
| Redis plugin | ~$5/mo |
| 6 Postgres databases | ~$15–30/mo |
| **Total** | **~$25–55/mo** |

> Costs vary based on usage. Railway's Hobby plan ($5/mo base) includes generous free compute. Use [railway.app/pricing](https://railway.app/pricing) for current rates.

---

*Last updated: 2025-11 — ZenSensei Backend v1.0*
