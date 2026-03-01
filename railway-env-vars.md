# ZenSensei Railway Environment Variables Reference

Complete reference of every environment variable needed for each Railway service.

> **Shared secret rule:** `SECRET_KEY` must be the same value across all services.
> Generate once with: `python -c "import secrets; print(secrets.token_hex(32))"`

## Gateway

| Variable | Description | Required |
|---|---|---|
| `PORT` | Injected by Railway | Auto |
| `ENVIRONMENT` | production | Required |
| `SECRET_KEY` | JWT signing secret | Required |
| `JWT_ALGORITHM` | HS256 | Required |
| `USER_SERVICE_URL` | Internal URL | Required |
| `GRAPH_QUERY_SERVICE_URL` | Internal URL | Required |
| `AI_REASONING_SERVICE_URL` | Internal URL | Required |
| `INTEGRATION_SERVICE_URL` | Internal URL | Required |
| `NOTIFICATION_SERVICE_URL` | Internal URL | Required |
| `ANALYTICS_SERVICE_URL` | Internal URL | Required |
| `ALLOWED_ORIGINS` | CORS origins | Required |

## User Service

| Variable | Description | Required |
|---|---|---|
| `PORT` | Injected by Railway | Auto |
| `ENVIRONMENT` | production | Required |
| `SECRET_KEY` | JWT signing secret | Required |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` | Required |
| `FIRESTORE_PROJECT_ID` | GCP project ID | Required |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to service account | Required |

## Graph Query Service

| Variable | Description | Required |
|---|---|---|
| `NEO4J_URI` | Bolt connection URI | Required |
| `NEO4J_USER` | neo4j | Required |
| `NEO4J_PASSWORD` | Database password | Required |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` | Required |

## Redis Plugin

| Reference Variable | Description |
|---|---|
| `${{Redis.REDIS_URL}}` | Full connection URL |
| `${{Redis.REDIS_HOST}}` | Hostname |
| `${{Redis.REDIS_PORT}}` | Port |
| `${{Redis.REDIS_PASSWORD}}` | Auth password |
