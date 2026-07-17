# Startup Guide

> **Last updated:** 2026-07-17

本文只保留当前仓库内可直接验证的启动方式与文件名。

---

## 最简演示模式

适用于本地演示，不依赖 PostgreSQL、Redis 或真实 API Key。

```bash
cp .env.demo .env
uv sync --all-extras
uv run uvicorn api.main:app --reload --port 8000
```

可选前端：

```bash
uv run streamlit run frontend/app.py --server.port 8501
```

说明：
- `.env.demo` 已启用 `LLM_MODE=mock`
- `.env.demo` 已启用 `STORAGE_BACKEND=sqlite`
- `.env.demo` 已启用 `DEFAULT_SCENARIO_ID=generic_rag_demo`
- `.env.demo` 不包含真实 API Key、数据库密码或证书私钥
- `JWT_SECRET` 仅适用于本地演示，不应复用于共享环境

如使用 Streamlit 前端，新建会话时可直接选择内置场景；列表来自后端 `/sessions/scenarios` 动态接口。

---

## 本地开发模式

使用真实 DeepSeek/Tavily，数据库与缓存通过 Docker 提供。

```bash
cp .env.example .env
docker compose up postgres redis -d
uv sync --all-extras
uv run uvicorn api.main:app --reload --port 8000
uv run streamlit run frontend/app.py --server.port 8501
```

必要配置：
- `.env` 中填写 `DEEPSEEK_API_KEY`
- `.env` 中填写 `TAVILY_API_KEY`
- `.env` 中填写 `POSTGRES_PASSWORD`
- `.env` 中填写长度至少 32 的 `JWT_SECRET`

---

## Docker 生产样式启动

当前仓库的 `docker-compose.yml` 使用 Docker secrets，而不是把这些敏感值直接写进 `.env`。

```bash
make setup    # 自动生成 .env（从 .env.example）、secrets/（从 secrets.example/）与 TLS 证书
make prod-up
```

若只需开发证书而不做完整 setup：

```bash
# Bash / Git Bash
./scripts/gen_certs.sh

# Windows PowerShell
powershell -ExecutionPolicy Bypass -File .\scripts\gen_certs.ps1
```

启动前需准备：
- `secrets/jwt_secret`
- `secrets/postgres_password`
- `secrets/redis_password`
- `secrets/deepseek_api_key`
- `secrets/tavily_api_key`
- `secrets/grafana_password`

验证：

```bash
curl -k https://localhost/api/health/live
```

---

## 登录方式

`POST /auth/login` 使用 `OAuth2PasswordRequestForm`，不是 JSON body。

注册：

```bash
curl -k -X POST https://localhost/api/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"admin@example.com\",\"password\":\"your-password\"}"
```

登录：

```bash
curl -k -X POST https://localhost/api/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "username=admin@example.com&password=your-password"
```

---

## 轻量 Docker 模式

若只想用 SQLite，可使用仓库现有的 `docker-compose.lite.yml`：

```bash
cp .env.demo .env
docker compose -f docker-compose.lite.yml up --build
```

该 compose 文件会默认以 `mock + sqlite + generic_rag_demo` 启动，并将前端 API 地址指向容器内 `http://api:8000`。

---

## 当前已知注意事项

- 执行 `uv sync --all-extras` 补齐依赖后，全量 `python -m pytest tests/ -q` 结果为 `650 passed, 1 skipped`（v1.3.0 实测，2026-07-17）。未安装 `prometheus_fastapi_instrumentator` 时会多跳过 5 个依赖该库的测试（合计 `6 skipped`）；该依赖实际位于 `pyproject.toml` 主依赖列表，而非可选依赖组。
- 未安装该依赖时的 `6 skipped` 中，4 个来自 `tests/test_gate_report.py` 对 `prometheus_fastapi_instrumentator` 的显式 `importorskip`，1 个来自 `tests/test_api.py` 对同一依赖的模块级 `importorskip`，1 个来自 `tests/test_health.py` 的其他依赖条件。
- `/health/ready` 在 `sqlite` 模式下会跳过 Redis 检查。
- 文档中所有 `.env.acceptance`、`.env.lite` 的旧提法均已失效，当前仓库实际跟踪的环境模板只有 `.env.example` 和 `.env.demo`。
