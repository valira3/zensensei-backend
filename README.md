# ZenSensei Backend

> Knowledge-graph-powered personal AI that understands your financial life, career, habits, and goals served via a clean microservices architecture on Google Cloud.

## Services

| Service | Port | Responsibility |
|---|---|---|
| `api_gateway` | 4000 | Request routing, auth, rate-limiting |
| `user_service` | 8001 | User CRUD, profile management |
| `graph_query_service` | 8002 | Neo4j queries, knowledge graph traversal |
| `ai_reasoning_service` | 8003 | Gemini integration, LLM reasoning |
| `integration_service` | 8004 | OAuth + external API connectors |
| `notification_service` | 8005 | Email, push, in-app alerts |
| `analytics_service` | 8006 | BigQuery pipeline, usage metrics |

## Tech Stack

- **Runtime**: Python 3.11, FastAPI, Uvicorn
- **Graph DB**: Neo4j 5.x
- **Cache**: Redis 7
- **Auth**: Firebase Identity Platform + JWT
- **AI**: Vertex AI / Gemini 1.5 Pro
- **Infra**: Google Cloud Run
