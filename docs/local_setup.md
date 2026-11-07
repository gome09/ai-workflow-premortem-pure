# Local Environment Setup Guide

> **Last updated:** 2026-11-01

**所有启动命令与验证步骤见 [startup.md](startup.md)**，本页不重复。这里只覆盖 startup.md 不含的三件事：环境模板、环境变量清单、仓库边界。

---

## 当前仓库存在的环境模板

只有两个：

- `.env.example`：真实接口与常规开发配置模板
- `.env.demo`：`mock + sqlite` 本地演示模板

当前仓库中不存在 `.env.acceptance` 或 `.env.lite`。旧文档如提及这两个文件名，均以上述两者替代。

四种启动方式各自使用哪个模板：

| 启动方式 | 配置来源 | 对应 startup.md 章节 |
|---|---|---|
| 离线演示（`make demo-api` / `demo-ui`） | `.env.demo`（**无条件覆盖** `.env`） | 最简演示模式 |
| 本地真实使用（本机 API + Docker DB） | `.env.example` + `make setup` 生成的 secrets | 本地开发模式 |
| Docker Lite（`make lite-up`） | `.env.demo`（仅 `.env` 不存在时复制） | 轻量 Docker 模式 |
| Docker Full（`make setup` + `make prod-up`） | `.env.example` + `secrets/` | Docker 生产样式启动 |

---

## 密钥与 secrets 的职责划分

- `make setup` 随机生成服务密钥及两把独立 Fernet key 写入 `secrets/`。
- 其中**前三个**会同步回 `.env` 的对应 `CHANGE_ME` 占位行——`.env` 的值会遮蔽容器内 `/run/secrets`，两处必须一致。自定义时必须同时改两处。
- `grafana_password` **不进入** `.env`，Grafana 容器经 `GF_SECURITY_ADMIN_PASSWORD__FILE` 直读 secrets 文件。
- `deepseek_api_key` / `tavily_api_key` 无法自动生成，保留占位文件；仅 `LLM_MODE=real` 时需手动填入。
- `data_encryption_key` / `checkpoint_encryption_key` 由 `make setup` 生成为不同的 Fernet key，经 Docker secrets 注入；非 Docker 部署可改用同名环境变量。启动后仍须核验字段加密和中断适配器健康状态。
- `secrets/` 不进入版本控制，由 `make setup` 从 `secrets.example/` 模板生成。
- `gen_secrets.sh` 默认将 secret 文件设为 `0600`。Linux 上若宿主文件属主与容器内非 root UID 不一致，应使用受控 ACL/属主映射授予读取权限；CI 对一次性随机密钥使用的 `0644` 规避方式**不应**照搬到生产长期密钥。

---

## 关键环境变量

| 变量 | 用途 | 当前代码状态 |
|------|------|--------------|
| `APP_ENV` | 运行环境 | 使用中，支持 `development` / `production`；`production` 下字段解密 fail-closed |
| `DEEPSEEK_API_KEY` | LLM 调用 | 使用中 |
| `TAVILY_API_KEY` | 搜索调用 | 使用中 |
| `JWT_SECRET` | JWT 签名 | 使用中，且必须 ≥ 32 字符 |
| `DOMAIN_PROFILE` | 领域配置 | 使用中，支持 `default` / `university_ai` / `medical_ai`；其他值会回落 default 并打 WARNING |
| `LLM_MODE` | 真实或 mock | 使用中，支持 `real` / `mock`，默认 `real` |
| `LLM_TIMEOUT_SECONDS` / `LLM_MAX_RETRIES` | 真实模型调用超时与 SDK 重试上限 | 默认 120 秒 / 1 次；超时或上游失败按固定错误码返回 502，`auth`/`bad_request` 标记为不可重试 |
| `STORAGE_BACKEND` | 存储后端 | 使用中，支持 `postgres` / `sqlite`，默认 `postgres` |
| `APP_ENV` | 运行环境 | 使用中；`production` 启动时拒绝 `LLM_MODE=mock`、`STORAGE_BACKEND=sqlite`、`DEMO_AUTO_AUTH=true` 及缺失/非法 `DATA_ENCRYPTION_KEY` |
| `POSTGRES_PORT` | 应用连接 PostgreSQL 的端口 | 使用中；容器内与本机原生 PG 用 `5432`，宿主进程连 Docker DB 用 `5433`（override 映射） |
| `SQLITE_PATH` | SQLite 文件路径 | 仅 SQLite 模式使用，默认 `data/workflow.db` |
| `WORKFLOW_EXECUTION_MODE` | 执行模式 | 使用中，默认 `single_step`；`langgraph_interrupt` 为显式 opt-in，非生产默认 |
| `CHECKPOINT_BACKEND` | LangGraph checkpoint 后端 | `postgres` 为持久化后端；`memory` 仅限 SQLite/本地开发，重启不可恢复 |
| `CHECKPOINT_ENCRYPTION_KEY` | checkpoint 独立 Fernet key | PostgreSQL 中断模式必填；不得与 `DATA_ENCRYPTION_KEY` 共用 |
| `INTERRUPT_RESUME_RETRY_INTERVAL_SECONDS` / `INTERRUPT_RESUME_RETRY_BATCH_SIZE` | 中断恢复 outbox 周期重试 | 仅 `langgraph_interrupt` 模式生效；默认 600 秒 / 100 行，设为 0 关闭周期重试 |
| `CORS_ALLOW_ORIGINS` | CORS 白名单 | 使用中 |
| `DEMO_AUTO_AUTH` | 固定演示账号自动认证 | 生产必须为 `false`；仅本地 demo/开发 override 可启用 |
| `UVICORN_WORKERS` | worker 数 | 使用中；`langgraph_interrupt` 当前必须为 `1` |
| `DATA_ENCRYPTION_KEY` | 字段级加密 Fernet key | PostgreSQL 或 `APP_ENV=production` 下缺失密钥时解密 fail-closed（`FieldDecryptionError`）；仅 SQLite 开发模式允许明文并告警 |
| `PII_MASK_BEFORE_LLM` | 送 LLM 前掩码 PII | 默认 `false`；聊天正文与补充材料命中四类 PII 会先升级 `sensitive_personal` 并强制掩码，本开关仅对未升级内容生效 |
| `AUDIT_RETENTION_DAYS` / `SESSION_RETENTION_DAYS` | 留存天数 | 使用中；到期数据由内置留存执行器按周期清理，`0` 表示永久保留 |
| `RETENTION_ENABLED` / `RETENTION_DRY_RUN` | 留存执行器开关 | `RETENTION_ENABLED` 默认 `true`；`RETENTION_DRY_RUN` 默认 `true`，只统计候选不删除，生产需显式改为 `false` |
| `RETENTION_SWEEP_INTERVAL_SECONDS` / `RETENTION_BATCH_SIZE` | 扫描周期与批次上限 | 默认 86400 秒、1000 行/会话；首次扫描在启动后一个周期执行 |
| `GATE_RULES_DISABLED` | 禁用门禁规则 | 使用中；安全底线规则配置了也会被忽略 |
| `EVAL_LLM_JUDGE` / `EVAL_LLM_JUDGE_AUTOFINAL` | LLM 建议判分 | 使用中，**默认均为 off** |
| `TARGET_SYSTEM_ALLOWED_HOSTS` | 真实目标系统 host 白名单 | 使用中；逗号分隔（`host` 或 `host:port`），**空值表示拒绝所有外部目标调用** |
| `TARGET_SYSTEM_TOKEN` | 真实目标系统 Bearer token | 可选；仅注入请求头，不写入上下文或审计 |
| `TARGET_SYSTEM_TIMEOUT_SECONDS` / `TARGET_SYSTEM_MAX_RESPONSE_CHARS` | 目标调用超时与响应截断 | 默认 10 秒、4000 字符 |

完整清单与默认值以 `core/config.py` 为准。

---

## 当前仓库边界

- `sqlite` 模式适合本地演示或轻量开发，不适合多进程高并发。
- `CHECKPOINT_BACKEND=memory` 不是持久化方案，API 进程重启后不能恢复已中断执行，不得用于生产。
- 不能只复制 `.env.example` 就启动数据库：compose 的 PostgreSQL / Redis 服务实际读取文件型 secrets，必须先跑 `make setup`。
- 当前与历史测试基线统一记录在 `docs/acceptance_report.md`。录制基线必须用 `uv run pytest` / `make test`；用系统 Python 直接跑会因缺主依赖产生虚假 skip 计数。
- `/health/ready` 在 `sqlite` 模式下会跳过 Redis 检查。
