# ZenSensei API Documentation

> **Base URL (production):** `https://api.zensensei.app`  
> **Base URL (staging):** `https://api-staging.zensensei.app`  
> **API Version:** `v1`

All endpoints are routed through the API Gateway at port **4000**. Individual services are accessible directly during local development.

## Authentication

All protected endpoints require a JWT Bearer token in the `Authorization` header:

```
Authorization: Bearer <access_token>
```

Tokens are obtained via `POST /api/v1/auth/login` or `POST /api/v1/auth/register`. Access tokens expire in **15 minutes**; use the refresh endpoint to obtain new tokens without re-authenticating.
