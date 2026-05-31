# Local Environment Setup Guide

> **Last updated:** 2026-05-30

This guide covers three environment configurations for the AI Workflow Pre-mortem platform.

---

## Environment Types

### 1. Acceptance / Deterministic Test Environment

**Purpose:** Docker Final Acceptance — deterministic testing with dummy keys.

**Characteristics:**
- Uses `.env.acceptance` with dummy DeepSeek / Tavily keys
- Runs via Docker Compose
- All deterministic checks pass (ruff, compileall, pytest, acceptance scripts)
- Does NOT prove real LLM / search connectivity
- PostgreSQL and Redis run as Docker containers

**When to use:** Running acceptance tests, CI validation, verifying code changes don't break existing tests.

### 2. Local Real-Use Environment

**Purpose:** Personal or small-team use with real AI capabilities.

**Characteristics:**
- Uses `.env` with real `DEEPSEEK_API_KEY` and `TAVILY_API_KEY`
- Can run via Docker Compose or local development mode
- Full Stage 1–4 workflow with real LLM and search
- PostgreSQL and Redis required

**When to use:** Actually using the platform for AI project pre-mortem analysis.

### 3. Production Environment

**Purpose:** Not currently supported.

**Requirements (NOT implemented):**
- Authentication / Authorization / RBAC
- Multi-tenant isolation
- Secrets management
- Rate limiting
- Production observability
- Load balancing / high availability

**Status:** Do NOT attempt production deployment. Target: v1.0.

---

## Prerequisites

- Docker and Docker Compose
- Python 3.11+
- `uv` (Python package manager)
- DeepSeek API key (for real use) — get from [platform.deepseek.com](https://platform.deepseek.com)
- Tavily API key (for real use) — get from [tavily.com](https://tavily.com)

---

## Setup: Acceptance Environment

```bash
# 1. Clone the repository
git clone <repo-url>
cd ai-workflow-premortem

# 2. Use the acceptance env file (dummy keys, Docker service names)
cp .env.acceptance .env

# 3. Start all services
docker compose up -d

# 4. Verify
curl http://localhost:8000/health
# Expected: {"status":"ok","version":"0.8.0-alpha.11",...}

# 5. Open frontend
# http://localhost:8501
```

---

## Setup: Local Real-Use Environment

### Option A: Docker (Recommended)

```bash
# 1. Clone the repository
git clone <repo-url>
cd ai-workflow-premortem

# 2. Copy and configure environment
cp .env.example .env
# Edit .env:
#   DEEPSEEK_API_KEY=sk-your-real-key
#   TAVILY_API_KEY=tvly-your-real-key
#   POSTGRES_PASSWORD=choose-a-password

# 3. Start all services
docker compose up -d

# 4. Verify
curl http://localhost:8000/health

# 5. Open frontend
# http://localhost:8501
```

### Option B: Local Development

```bash
# 1. Install dependencies
uv sync --all-extras

# 2. Copy and configure environment
cp .env.example .env
# Edit .env with real keys
# For local dev, POSTGRES_HOST=localhost, REDIS_HOST=localhost

# 3. Start PostgreSQL and Redis (via Docker)
docker compose up postgres redis -d

# 4. Start API
uv run uvicorn api.main:app --reload --port 8000

# 5. Start Streamlit (in a separate terminal)
uv run streamlit run frontend/app.py --server.port 8501
```

---

## Environment Variable Reference

See `.env.example` for the complete list. Key variables:

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `DEEPSEEK_API_KEY` | Yes | — | Real key for LLM calls |
| `TAVILY_API_KEY` | Yes | — | Real key for search |
| `POSTGRES_HOST` | No | `localhost` | Use `postgres` in Docker |
| `POSTGRES_PORT` | No | `5432` | — |
| `POSTGRES_DB` | No | `ai_workflow` | — |
| `POSTGRES_USER` | No | `postgres` | — |
| `POSTGRES_PASSWORD` | Yes | — | — |
| `REDIS_HOST` | No | `localhost` | Use `redis` in Docker |
| `REDIS_PORT` | No | `6379` | — |
| `REDIS_PASSWORD` | No | — | — |
| `REDIS_DB` | No | `0` | — |
| `APP_ENV` | No | `development` | `development` / `production` |
| `LOG_LEVEL` | No | `INFO` | — |
| `SESSION_TTL_HOURS` | No | `72` | — |
| `API_BASE` | No | `http://localhost:8000` | Use `http://api:8000` in Docker |
| `STAGE_OUTPUT_MODE` | No | `json_first` | — |
| `WORKFLOW_EXECUTION_MODE` | No | `single_step` | `single_step` / `langgraph_interrupt` |

### Docker vs Local Differences

| Variable | Docker Value | Local Value |
|----------|-------------|-------------|
| `POSTGRES_HOST` | `postgres` | `localhost` |
| `REDIS_HOST` | `redis` | `localhost` |
| `API_BASE` (frontend) | `http://api:8000` | `http://localhost:8000` |

When using Docker Compose, these are set automatically via `environment:` in `docker-compose.yml`. The `.env` values are overridden for the frontend container.

---

## Missing API Key Behavior

- **DeepSeek API Key missing:** LLM calls fail. Stage 1–4 return configuration errors.
- **Tavily API Key missing:** Search (Stage 1 failure mode search) unavailable.
- **PostgreSQL unavailable:** Full API startup fails. Tests use in-memory storage.
- **Redis unavailable:** Cache degrades; core flow unaffected.

---

## Switching Between Environments

```bash
# Switch to acceptance env
cp .env.acceptance .env
docker compose down
docker compose up -d

# Switch to real-use env
cp .env.example .env
# Edit with real keys
docker compose down
docker compose up -d
```

---

## Troubleshooting

See [startup.md](startup.md) for common startup issues and solutions.
