# Getting Started

## Prerequisites

- Python 3.11+
- Docker 24+ and Docker Compose v2
- GNU Make
- GCP project (for cloud features)

## Local Setup

1. Clone the repository:
```bash
git clone https://github.com/valira3/zensensei-backend.git
cd zensensei-backend
```

2. Copy and configure environment:
```bash
cp .env.example .env
# Edit .env with your credentials
```

3. Start the local stack:
```bash
make up
```

4. Seed the database:
```bash
make db-seed
```

5. Test the API:
```bash
curl http://localhost:4000/health
```

## Development Workflow

```bash
make install     # Install all dependencies
make lint        # Run linting
make format      # Auto-fix formatting
make test        # Run tests
make test-cov    # Run tests with coverage
```

## Environment Variables

See `.env.example` for all required variables.
