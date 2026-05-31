# Startup Guide

> **Last updated:** 2026-05-30

This guide covers starting, verifying, and stopping the AI Workflow Pre-mortem platform.

---

## Recommended Docker Startup

### First-Time Setup

```bash
# 1. Clone and enter directory
git clone <repo-url>
cd ai-workflow-premortem

# 2. Configure environment
cp .env.example .env
# Edit .env:
#   DEEPSEEK_API_KEY=your_key       (real key for live use, or dummy for testing)
#   TAVILY_API_KEY=your_key         (real key for live use, or dummy for testing)
#   POSTGRES_PASSWORD=your_password

# 3. Build and start all services
docker compose up -d --build

# 4. Wait for services to be healthy (typically 10-30 seconds)
docker compose ps
```

### Verify Services

```bash
# API health check
curl -f http://localhost:8000/health
# Expected: {"status":"ok","version":"0.8.0-alpha.11",...}

# OpenAPI spec
curl -f http://localhost:8000/openapi.json
# Expected: OpenAPI 3.1.0 JSON spec

# Frontend
# Open http://localhost:8501 in browser
```

### Check Logs

```bash
# All services
docker compose logs -f

# API only
docker compose logs -f api

# Frontend only
docker compose logs -f frontend

# Last 50 lines
docker compose logs --tail=50 api
```

### Stop Services

```bash
# Stop all services
docker compose down

# Stop and remove volumes (fresh start)
docker compose down -v
```

---

## Acceptance Mode

Uses `.env.acceptance` with dummy keys. For running deterministic checks only — does NOT validate real LLM / search connectivity.

```bash
cp .env.acceptance .env
docker compose up -d --build

# Verify
curl http://localhost:8000/health
```

---

## Real Local-Use Mode

Requires real DeepSeek and Tavily API keys.

```bash
cp .env.example .env
# Edit .env with real keys

docker compose up -d --build

# Verify
curl http://localhost:8000/health

# Open frontend
# http://localhost:8501
```

### Quick Live Smoke

After starting with real keys:

1. Open `http://localhost:8501`
2. Create a new session
3. Run Stage 1 (Failure Mode Identification)
4. Verify DeepSeek responds with analysis
5. Verify Tavily search results appear in the output

If both work, the platform is ready for real use.

---

## Local Development Mode (without Docker)

```bash
# Install dependencies
uv sync --all-extras

# Start PostgreSQL and Redis via Docker
docker compose up postgres redis -d

# Configure .env for local dev
cp .env.example .env
# POSTGRES_HOST=localhost
# REDIS_HOST=localhost
# API_BASE=http://localhost:8000

# Start API (in terminal 1)
uv run uvicorn api.main:app --reload --port 8000

# Start Streamlit (in terminal 2)
uv run streamlit run frontend/app.py --server.port 8501
```

---

## Docker Service Architecture

| Service | Container | Port | Health Check |
|---------|-----------|------|-------------|
| PostgreSQL | `aiwf_postgres` | 5432 | `pg_isready -U postgres` |
| Redis | `aiwf_redis` | 6379 | `redis-cli ping` |
| API | `aiwf_api` | 8000 | `GET /health` |
| Frontend | `aiwf_frontend` | 8501 | Streamlit built-in |

**Dependency order:** postgres → redis → api → frontend

---

## Common Troubleshooting

### API fails to start

**Symptom:** `aiwf_api` container exits or health check fails.

**Common causes:**
- PostgreSQL not ready yet — wait 10 seconds and check `docker compose ps`
- Wrong `POSTGRES_PASSWORD` in `.env` — must match what PostgreSQL container uses
- Port 8000 already in use — stop other services on that port

```bash
# Check API logs
docker compose logs api

# Restart API
docker compose restart api
```

### Frontend can't reach API

**Symptom:** Streamlit shows connection errors.

**Common causes:**
- API not started yet — check `docker compose ps`
- `API_BASE` not set correctly — in Docker, should be `http://api:8000` (set automatically in docker-compose.yml)

### PostgreSQL connection refused

**Symptom:** API logs show `connection refused` for PostgreSQL.

**Common causes:**
- PostgreSQL container not healthy — `docker compose logs postgres`
- Wrong host — in Docker, use `postgres` (not `localhost`)
- Port conflict — another PostgreSQL instance on host port 5432

### Redis connection refused

**Symptom:** Cache warnings in API logs.

**Common causes:**
- Redis container not running — `docker compose ps`
- Wrong host — in Docker, use `redis` (not `localhost`)

### Fresh restart

```bash
# Stop everything, remove volumes, rebuild
docker compose down -v
docker compose up -d --build
```

### View container status

```bash
docker compose ps
# All services should show "Up" and (healthy) for postgres/redis
```

---

## Running Tests

```bash
# Via Docker
docker compose run --rm api uv run pytest tests/ -q

# Locally
uv run pytest tests/ -q
```

Tests use in-memory storage and monkeypatched LLM — no real keys or services needed.
