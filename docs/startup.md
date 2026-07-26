# Startup Guide

> **Last updated:** 2026-07-27

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
make setup
# 编辑 .env：设置 DEEPSEEK_API_KEY / TAVILY_API_KEY；setup 已同步 JWT/PG/Redis 密码
docker compose up postgres redis -d
uv sync --all-extras
uv run uvicorn api.main:app --reload --port 8000
uv run streamlit run frontend/app.py --server.port 8501
```

`postgres` / `redis` compose 服务读取 `secrets/postgres_password` 与 `secrets/redis_password`，因此仅复制 `.env.example` 不足以启动它们。`make setup` 会创建文件型 secrets，并把 PostgreSQL、Redis 和 JWT 的同值配置同步进 `.env`；本机运行 API 时仍需在 `.env` 设置真实 DeepSeek/Tavily key。

---

## Docker 生产样式启动

当前 `docker-compose.yml` 挂载文件型 secrets；为兼容应用的配置优先级，setup 还会把 JWT、PostgreSQL、Redis 三项同步进 `.env`，并非所有敏感值都只存在于 secrets 文件。

```bash
make setup    # 自动生成 .env、secrets/（jwt/postgres/redis/grafana 四个密钥随机生成，前三者同步 .env）与 TLS 证书
make prod-up  # 启动前自动做前置检查（secrets/ 六文件 + 证书存在性；示例占位值仅警告）
```

说明：
- `make setup` 会调用 `scripts/gen_secrets.sh`：`jwt_secret` / `postgres_password` / `redis_password` / `grafana_password` 用 `openssl rand -hex 32` 随机生成；其中前三者会把 `.env` 中对应的 `CHANGE_ME` 占位行同步为相同值（`.env` 值会遮蔽容器内 `/run/secrets`，两处必须一致），`grafana_password` 不涉及 `.env`（Grafana 容器直接经 `GF_SECURITY_ADMIN_PASSWORD__FILE` 读取 secrets 文件）；`deepseek_api_key` / `tavily_api_key` 无法生成，保留占位文件，`LLM_MODE=real` 时需手动填入真实值。
- `make setup` **不会生成** `DATA_ENCRYPTION_KEY`。PostgreSQL 生产部署如需字段加密，按 `.env.example` 注释生成 Fernet key 并写入 `.env`；启动后检查 `/health` 的 `data_encryption` 必须为 `enabled`。为空时应用只告警并继续明文存储。
- `make prod-up` 前置检查失败（缺 secrets 文件或证书）会直接报错并提示先跑 `make setup`，不会进入晦涩的 compose 挂载错误。
- `gen_secrets.sh` 默认将 secret 文件设为 `0600`。Linux 主机若宿主用户与容器内非 root UID 不同，需由部署方用受控 ACL/属主映射确保容器可读；不要在生产环境把长期密钥直接改成全局可读。

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

- 当前测试基线及带日期的历史快照见 `docs/acceptance_report.md`；测试数量会随集合变化，应以本地命令输出和 skip reason 为准。
- `/health/ready` 在 `sqlite` 模式下会跳过 Redis 检查。
- 文档中所有 `.env.acceptance`、`.env.lite` 的旧提法均已失效，当前仓库实际跟踪的环境模板只有 `.env.example` 和 `.env.demo`。
