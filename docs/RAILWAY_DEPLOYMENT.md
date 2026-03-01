# Railway Deployment Guide

## Overview

This guide covers deploying ZenSensei backend services to Railway.

## Prerequisites

- Railway account
- Railway CLI installed
- GitHub repository connected

## Services

Each microservice has its own Railway configuration in `railway-configs/`.

## Deployment Steps

1. Install Railway CLI:
```bash
npm install -g @railway/cli
```

2. Login:
```bash
railway login
```

3. Deploy all services:
```bash
./scripts/deploy-railway.sh
```

## Environment Variables

Set the following in Railway dashboard:
- `NEO4J_URI`
- `NEO4J_USER`
- `NEO4J_PASSWORD`
- `REDIS_URL`
- `SECRET_KEY`
- `FIREBASE_PROJECT_ID`

See `railway-env-vars.md` for the complete list.

## Service URLs

After deployment, Railway will assign URLs like:
- `https://api-gateway.up.railway.app`
- `https://user-service.up.railway.app`
- etc.
