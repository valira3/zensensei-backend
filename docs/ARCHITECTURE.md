# ZenSensei Architecture

## Overview

ZenSensei is a microservices-based backend platform that uses a knowledge graph to power personal AI reasoning.

## Services

- **API Gateway** (port 4000): JWT auth, rate limiting, request routing
- **User Service** (port 8001): User management and profiles
- **Graph Query Service** (port 8002): Neo4j knowledge graph queries
- **AI Reasoning Service** (port 8003): Gemini/Vertex AI integration
- **Integration Service** (port 8004): OAuth and external API connectors
- **Notification Service** (port 8005): Email, push, and in-app alerts
- **Analytics Service** (port 8006): BigQuery pipeline and metrics

## Data Flow

1. Client sends request to API Gateway
2. Gateway validates JWT and routes to appropriate service
3. Services query Neo4j knowledge graph as needed
4. AI Reasoning Service uses Vertex AI/Gemini for LLM calls
5. Results returned through Gateway to client

## Infrastructure

- **Database**: Neo4j AuraDB (knowledge graph)
- **Cache**: Redis 7
- **Auth**: Firebase Identity Platform
- **AI**: Vertex AI / Gemini 1.5 Pro
- **Deploy**: Google Cloud Run
- **IaC**: Terraform
