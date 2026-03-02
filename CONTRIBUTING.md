# Contributing to ZenSensei Backend

Thank you for your interest in contributing! This guide covers everything you need to get started.

---

## Setup

### Prerequisites

- Python 3.12+
- Docker Desktop
- Redis (via Docker or local install)
- Make

### Local development environment

```bash
git clone https://github.com/zensensei/zensensei-backend.git
cd zensensei-backend

# Install Python dependencies
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt

# Copy and configure environment
cp .env.example .env

# Start the full stack
make dev

# Verify everything is running
curl http://localhost:4000/health
```

---

## Coding Standards

### Style and formatting

- **Formatter:** `black` (line length 100) — run `black .` before committing
- **Linter:** `ruff` — run `ruff check .` before committing
- **Type checker:** `mypy` (strict mode on `shared/`) — run `mypy shared/ services/ gateway/`
- All three must pass before opening a PR

### Python conventions

- Use type annotations on all public functions and methods
- Use `async`/`await` for I/O-bound operations (FastAPI endpoints, database calls)
- Use `structlog` for logging — never `print()` in production code
- Use Pydantic models for request/response validation
- Keep service boundaries clean — services must not import from other services directly (use shared/ only)

### Commit message format

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(user-service): add OAuth Google login
fix(graph-query): handle disconnected Neo4j gracefully
docs(api): add missing response examples for /insights
test(ai-reasoning): add unit tests for insight scoring
chore(deps): bump fastapi from 0.108.0 to 0.109.0
```

**Types:** `feat`, `fix`, `docs`, `test`, `chore`, `refactor`, `perf`, `ci`

---

## PR Process

1. **Fork** the repository and create your branch from `develop`:
   ```bash
   git checkout -b feat/my-feature develop
   ```

2. **Write tests** for any new behavior. Aim for meaningful coverage, not just high percentages.

3. **Run the full check suite** locally before pushing:
   ```bash
   make lint    # ruff + black + mypy
   make test    # pytest with coverage
   ```

4. **Open a PR to `develop`** (not `main`). Fill in the PR template:
   - What problem does this solve?
   - How was it tested?
   - Any breaking changes or migration steps?

5. **Review requirements:**
   - PRs to `develop`: 1 reviewer approval + passing CI
   - PRs to `main`: 2 reviewer approvals + passing CI + no open security alerts

6. **Keep PRs focused** — one feature or fix per PR. Large PRs are harder to review and slower to merge.

---

## Security

If you discover a security vulnerability, **do not open a public issue**. Email security@zensensei.net instead. See [SECURITY.md](SECURITY.md) for the full policy.

---

## Questions

Open a [GitHub Discussion](https://github.com/zensensei/zensensei-backend/discussions) for questions, ideas, or design feedback.
