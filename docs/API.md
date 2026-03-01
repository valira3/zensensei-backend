# ZenSensei API Documentation

> **Base URL (production):** `https://api.zensensei.app`
> **API Version:** `v1`

All endpoints require a Bearer token in the Authorization header.

## Authentication

### POST /api/v1/auth/register
Create a new user account.

### POST /api/v1/auth/login
Authenticate and receive JWT tokens.

### POST /api/v1/auth/refresh
Refresh access token using refresh token.

## Users

### GET /api/v1/users/me
Get current user profile.

### PATCH /api/v1/users/me
Update current user profile.

## Graph

### GET /api/v1/graph/query
Execute a knowledge graph query.

## AI

### POST /api/v1/ai/reason
Submit a reasoning request to the AI service.

## Integrations

### GET /api/v1/integrations
List connected integrations.

### POST /api/v1/integrations/{provider}/connect
Connect a new integration.
