# Local Environment Setup Guide

> **Last updated:** 2026-06-08

---

## 当前仓库存在的环境模板

只有两个：

- `.env.example`：真实接口与常规开发配置模板
- `.env.demo`：`mock + sqlite` 本地演示模板

当前仓库中不存在 `.env.acceptance` 或 `.env.lite`。

---

## 方案 1：演示环境

```bash
cp .env.demo .env
uv sync --all-extras
uv run uvicorn api.main:app --reload --port 8000
```

特征：
- `LLM_MODE=mock`
- `STORAGE_BACKEND=sqlite`
- `DEFAULT_SCENARIO_ID=generic_rag_demo`
- 不依赖 PostgreSQL / Redis / 外部 API Key
- 不依赖真实证书或私钥

---

## 方案 2：本地真实使用环境

```bash
cp .env.example .env
docker compose up postgres redis -d
uv sync --all-extras
uv run uvicorn api.main:app --reload --port 8000
uv run streamlit run frontend/app.py --server.port 8501
```

需要填写：
- `DEEPSEEK_API_KEY`
- `TAVILY_API_KEY`
- `POSTGRES_PASSWORD`
- `JWT_SECRET`

---

## 方案 3：Docker Lite（SQLite + Mock）

使用 `docker-compose.lite.yml`，无需 PostgreSQL / Redis，适合快速演示：

```bash
# 自动将 .env.demo 复制为 .env（如尚未存在）
make lite-up
```

配置来源为 `.env.demo`（`LLM_MODE=mock`，`STORAGE_BACKEND=sqlite`）。

---

## 方案 4：Docker Full（PostgreSQL + Redis + 真实 LLM）

使用 `docker-compose.yml`，敏感值来自 Docker secrets。

一键初始化 `.env`、`secrets/` 和 TLS 证书：

```bash
make setup
```

该命令会：
- 若 `.env` 不存在，从 `.env.example` 复制
- 若 `secrets/` 不存在，从 `secrets.example/` 复制
- 签发开发用 TLS 证书

然后编辑以下文件填入真实值：
- `secrets/deepseek_api_key`
- `secrets/tavily_api_key`
- `secrets/jwt_secret`
- `secrets/postgres_password`
- `secrets/redis_password`
- `secrets/grafana_password`

> **注意：** `secrets/` 目录不进入版本控制（已在 `.gitignore` 中排除），提交包中不包含任何真实密钥。

启动服务：

```bash
make prod-up
curl -k https://localhost/api/health/live
```

开发 HTTPS 证书由 `make setup` 自动生成，如需手动生成：

```bash
# Bash / Git Bash
./scripts/gen_certs.sh

# Windows PowerShell
powershell -ExecutionPolicy Bypass -File .\scripts\gen_certs.ps1
```

---

## 关键环境变量

| 变量 | 用途 | 当前代码状态 |
|------|------|--------------|
| `DEEPSEEK_API_KEY` | LLM 调用 | 使用中 |
| `TAVILY_API_KEY` | 搜索调用 | 使用中 |
| `JWT_SECRET` | JWT 签名 | 使用中，且必须 ≥ 32 字符 |
| `DOMAIN_PROFILE` | 领域配置 | 使用中，支持 `default` / `university_ai` / `medical_ai` |
| `LLM_MODE` | 真实或 mock | 使用中，支持 `real` / `mock` |
| `STORAGE_BACKEND` | 存储后端 | 使用中，支持 `postgres` / `sqlite` |
| `DEFAULT_SCENARIO_ID` | 新建会话默认内置场景 | 使用中，可为空 |
| `WORKFLOW_EXECUTION_MODE` | 执行模式 | 使用中，默认 `single_step`；`langgraph_interrupt` 为实验性 opt-in 路径，非生产默认 |
| `CORS_ALLOW_ORIGINS` | CORS 白名单 | 使用中 |
| `UVICORN_WORKERS` | worker 数 | 使用中 |
| `FIRST_ADMIN_EMAIL` | 已删除 | 不再使用 |
| `FIRST_ADMIN_PASSWORD` | 已删除 | 不再使用 |

---

## 登录接口注意事项

`POST /auth/login` 不是 JSON 登录，而是表单登录：

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "username=admin@example.com&password=your-password"
```

注册接口才是 JSON body：

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"admin@example.com\",\"password\":\"your-password\"}"
```

---

## 当前仓库边界

- `sqlite` 模式适合本地演示或轻量开发，不适合多进程高并发。
- `docker-compose.lite.yml` 存在，轻量 Docker 模式使用 `.env.demo` 配置（`make lite-up` 自动复制）。
- Docker Full 模式使用 `.env.example` + `secrets/`（`make setup` 自动生成）。
- `secrets/` 目录不进入版本控制，由 `make setup` 从 `secrets.example/` 模板生成。
- 当前本地环境缺少 `prometheus_fastapi_instrumentator` 时，`tests/test_health.py` 与 `tests/test_api.py` 会失败。
