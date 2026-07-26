# Local Environment Setup Guide

> **Last updated:** 2026-07-27

---

## 当前仓库存在的环境模板

只有两个：

- `.env.example`：真实接口与常规开发配置模板
- `.env.demo`：`mock + sqlite` 本地演示模板

当前仓库中不存在 `.env.acceptance` 或 `.env.lite`。

---

## 方案 1：演示环境

可复制的 API、前端启动与验证步骤统一见 [startup.md](startup.md)。本页只补充环境模板、密钥和平台差异。

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
make setup
# 编辑 .env：设置 DEEPSEEK_API_KEY / TAVILY_API_KEY
docker compose up postgres redis -d
uv sync --all-extras
uv run uvicorn api.main:app --reload --port 8000
uv run streamlit run frontend/app.py --server.port 8501
```

需要填写：
- `DEEPSEEK_API_KEY`
- `TAVILY_API_KEY`
- `POSTGRES_PASSWORD` / `REDIS_PASSWORD` / `JWT_SECRET` 由 setup 生成并在 secrets 与 `.env` 间同步；需要自定义时必须保持两处一致

不能只复制 `.env.example` 后启动数据库：compose 的 PostgreSQL/Redis 服务实际读取文件型 secrets。

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

使用 `docker-compose.yml`。六项文件型 secrets 会挂载进容器，其中 JWT/PostgreSQL/Redis 三项还会同步进 `.env`；两处都属于需要保护和轮换的敏感面。

一键初始化 `.env`、`secrets/` 和 TLS 证书：

```bash
make setup
```

该命令会：
- 若 `.env` 不存在，从 `.env.example` 复制
- 若 `secrets/` 不存在，从 `secrets.example/` 复制
- 调用 `scripts/gen_secrets.sh`：随机生成 `jwt_secret` / `postgres_password` / `redis_password` / `grafana_password`（`openssl rand -hex 32`），并把 `.env` 中 `JWT_SECRET` / `POSTGRES_PASSWORD` / `REDIS_PASSWORD` 的 `CHANGE_ME` 占位行同步为相同值（`grafana_password` 仅写 secrets 文件，Grafana 经 `GF_SECURITY_ADMIN_PASSWORD__FILE` 直接读取，不经过 `.env`）
- 不生成 `DATA_ENCRYPTION_KEY`；生产如需字段加密，需按 `.env.example` 注释生成 Fernet key 并写入 `.env`
- 签发开发用 TLS 证书

然后仅在 `LLM_MODE=real` 时需要编辑以下文件填入真实值（mock 模式可跳过）：
- `secrets/deepseek_api_key`
- `secrets/tavily_api_key`

> **注意：** `secrets/` 目录不进入版本控制（已在 `.gitignore` 中排除），提交包中不包含任何真实密钥。

`gen_secrets.sh` 默认使用 `0600`。Linux 上若宿主文件属主与容器内非 root UID 不一致，应使用受控 ACL/属主映射授予容器读取权限；CI 对一次性密钥使用的 `0644` 规避方式不应直接照搬到生产长期密钥。

启动服务：

```bash
make prod-up   # 前置检查（secrets/ 六文件 + TLS 证书存在性）通过后启动；缺失时报错提示先跑 make setup
curl -k https://localhost/api/health/live
```

生产启动后还应检查 `curl -k https://localhost/api/health`，确认 `data_encryption` 为 `enabled`；若为 `disabled`，业务材料会按明文写入存储。

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
- 当前与历史测试基线统一记录在 `docs/acceptance_report.md`；测试文件增删后，以实际收集和执行结果为准。
