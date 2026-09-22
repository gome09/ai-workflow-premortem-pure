# Startup Guide

> **Last updated:** 2026-07-31

本文只保留当前仓库内可直接验证的启动方式与文件名，是**启动与部署步骤的单一权威来源**。环境模板说明、环境变量清单与仓库边界见 [local_setup.md](local_setup.md)。

---

## 最简演示模式

适用于本地演示，不依赖 PostgreSQL、Redis 或真实 API Key。

```bash
uv sync --all-extras
make demo-api                 # 后端
make demo-ui                  # 前端，另开终端
```

等价的手动命令：

```bash
cp .env.demo .env
uv sync --all-extras
uv run uvicorn api.main:app --reload --port 8000
uv run streamlit run frontend/app.py --server.port 8501
```

> ⚠️ `make demo-api` / `make demo-ui` 使用 `cp -f`，每次都会**无条件覆盖**现有 `.env`；`make lite-up` / `make prod-up` 则是仅在 `.env` 不存在时才复制。跑过 `make setup` 之后再跑演示模式，会丢失 `.env` 里由 `gen_secrets.sh` 同步的 JWT / PostgreSQL / Redis 值（`secrets/` 下的文件不受影响）。

说明：
- `.env.demo` 已启用 `LLM_MODE=mock`
- `.env.demo` 已启用 `STORAGE_BACKEND=sqlite`
- `.env.demo` 保持 `WORKFLOW_EXECUTION_MODE=single_step`；其 `CHECKPOINT_BACKEND=memory` 仅为本地实验预留，不保证进程重启恢复
- 在工作台选择内置场景后会立即创建并加载对应样例；“新建空白会话”不会附加任何内置场景
- `.env.demo` 不包含真实 API Key、数据库密码或证书私钥
- `JWT_SECRET` 仅适用于本地演示，不应复用于共享环境

如使用 Streamlit 前端，选择内置场景后会立即创建并加载场景会话；列表来自后端 `/sessions/scenarios` 动态接口。点击“新建空白会话”则不会加载场景或自动发送消息。

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
make setup    # 自动生成 .env、8 个 secrets（含两把独立 Fernet key）与 TLS 证书
make prod-up  # 启动前自动做前置检查（secrets/ 八文件 + 证书存在性；示例占位值仅警告）
```

说明：
- `make setup` 会调用 `scripts/gen_secrets.sh`：`jwt_secret` / `postgres_password` / `redis_password` / `grafana_password` 使用随机十六进制值；其中前三者会同步 `.env` 中对应的 `CHANGE_ME` 占位行，`grafana_password` 由 Grafana 容器直接读取。
- `data_encryption_key` 与 `checkpoint_encryption_key` 会生成为两把独立 Fernet key，并以 Docker secrets 挂入 API；环境变量仍具有更高优先级，非 Docker 部署可按 `.env.example` 显式设置。启动后必须确认 `/health.data_encryption=enabled`；启用中断模式还需确认 adapter 显示 persistent/encrypted/healthy。
- `deepseek_api_key` / `tavily_api_key` 无法生成，保留占位文件，`LLM_MODE=real` 时需手动填入真实值。
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
- `secrets/data_encryption_key`
- `secrets/checkpoint_encryption_key`

验证：

```bash
curl -k https://localhost/api/health/live
```

---

## 启用 LangGraph 中断模式

`single_step` 仍是默认稳定路径。启用持久化中断/恢复前，先确保 PostgreSQL 迁移已到最新 head，然后设置：

```bash
WORKFLOW_EXECUTION_MODE=langgraph_interrupt
STORAGE_BACKEND=postgres
CHECKPOINT_BACKEND=postgres
# Docker Full 默认从 /run/secrets/checkpoint_encryption_key 读取；
# 非 Docker 部署才需要设置 CHECKPOINT_ENCRYPTION_KEY。
UVICORN_WORKERS=1
```

非 Docker 部署生成独立 key（不得复用 `DATA_ENCRYPTION_KEY`）：

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Docker Full 的开启顺序（先由一次性容器迁移，再创建 API）：

```bash
docker compose up -d postgres
docker compose run --rm api python -m alembic upgrade head
docker compose up -d --build api frontend nginx redis prometheus grafana
curl -k https://localhost/api/health/ready
```

只有 readiness 成功且健康响应确认执行模式为 `langgraph_interrupt`、checkpoint 后端为持久化 PostgreSQL 时，才应开放工作流请求。配置不合法、checkpoint 表或数据库不可用、加密 key 缺失时应用应 fail closed，不会静默降级到内存 checkpoint。

生产 Compose 强制 `DEMO_AUTO_AUTH=false`，前端显示交互式登录/注册表单。只有开发 override 与 `.env.demo` 显式启用固定演示账号自动认证；生产不得开启该选项。

本地 SQLite 可用于功能调试，但不可用于持久化恢复或生产：

```bash
APP_ENV=development
WORKFLOW_EXECUTION_MODE=langgraph_interrupt
STORAGE_BACKEND=sqlite
CHECKPOINT_BACKEND=memory
CHECKPOINT_ENCRYPTION_KEY=
UVICORN_WORKERS=1
```

### 回滚到单步路径

先停止接收新请求，确认主业务存储中的 `PendingHumanAction` 完整，然后仅将执行模式改回：

```bash
WORKFLOW_EXECUTION_MODE=single_step
```

重启 API 并再次检查 `/health/ready`。回滚时不删除 checkpoint 表；保留数据用于审计和排障，且避免尚未完成的人工动作丢失。

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

## 轻量 Docker 模式（Lite / SQLite）

Lite mode 指 `STORAGE_BACKEND=sqlite`，无需 PostgreSQL、Redis 或 TLS 证书。

```bash
make lite-up          # 若 .env 不存在，自动从 .env.demo 复制
```

等价的手动命令：

```bash
cp .env.demo .env
docker compose -f docker-compose.lite.yml up --build
```

该 compose 文件会默认以 `mock + sqlite` 启动，并将前端 API 地址指向容器内 `http://api:8000`。内置场景由工作台显式选择并加载。

如需在 SQLite 上使用真实 API Key，从 `.env.example` 派生并手工加入：

```bash
STORAGE_BACKEND=sqlite
UVICORN_WORKERS=1
```

### 适用边界

适合：本地演示、答辩或功能展示、无 PostgreSQL / Redis 的轻量开发。

不适合：多进程高并发、生产部署、需要独立 Redis 缓存一致性的场景。

### 代码对应关系

| 文件 | 用途 |
|------|------|
| `storage/backends/sqlite_store.py` | SQLite 会话存储 |
| `storage/backends/memory_cache.py` | 进程内缓存 |
| `storage/session_store.py` | 后端工厂 |
| `storage/cache.py` | 缓存工厂 |
| `docker-compose.lite.yml` | 轻量 Docker 入口 |

---

## 当前已知注意事项

- 当前测试基线及带日期的历史快照见 `docs/acceptance_report.md`；测试数量会随集合变化，应以本地命令输出和 skip reason 为准。
- `/health/ready` 在 `sqlite` 模式下会跳过 Redis 检查。
- 文档中所有 `.env.acceptance`、`.env.lite` 的旧提法均已失效，当前仓库实际跟踪的环境模板只有 `.env.example` 和 `.env.demo`。
