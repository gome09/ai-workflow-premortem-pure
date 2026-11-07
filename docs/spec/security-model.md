# Security Model

> **Last updated:** 2026-11-01

> Status: Implemented

This project has two security layers:

1. **Infrastructure security**: authentication, RBAC, tenant isolation, secrets, reverse proxy, rate limiting
2. **Workflow safety**: SafetyFinding, PendingHumanAction, Stage Gate, evidence and eval governance

---

## Part 1: Infrastructure Security

### Authentication

认证实现位于 `auth/`，API 采用 JWT Bearer Token。人类用户与机器调用分离：人类使用 access/refresh JWT；发布门禁使用独立的租户级服务凭证（`Authorization: Bearer pmgate_...`），两者不可互换。

| Token Type | Lifetime | Purpose |
|------------|----------|---------|
| Access token | 15 minutes | Authenticate API requests |
| Refresh token | 7 days | Obtain a new access token |

当前接口：
- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/invitations`（admin only；原始 token 只返回一次）
- `GET /auth/invitations`（admin only；不返回 token）
- `POST /auth/invitations/accept`（公开端点 + 限流）

注意：
- `POST /auth/login` 使用 `OAuth2PasswordRequestForm`
- 登录请求是 `application/x-www-form-urlencoded`
- 不是 JSON body 登录

### RBAC

当前不是“同租户内所有用户权限等价”。

后端实现了 3 个角色：
- `viewer`
- `editor`
- `admin`

权限边界由 `auth/permissions.py` 和各 router 的依赖控制：
- `viewer`：只读
- `editor`：可创建/推进会话、提交人工动作、运行评测
- `admin`：额外拥有用户管理等高权限操作

每次注册都会创建独立工作区，创建者固定为 `admin`。同租户成员只能通过 `workspace_invitations` 加入（原始 token 只返回一次，数据库仅存 SHA-256，有效期 7 天）；不提供多工作区切换。`/auth/refresh` 重新读取当前用户记录并签发当前角色，不沿用旧刷新令牌中的 role。EvalRun 人工校准的复核人只取 JWT `user_id`，请求体不接受 `reviewer_id`。

### Service Tokens and Release Gate

发布门禁 `GET /release-gate/{session_id}` 只接受租户级服务凭证，不接受任何人类 access/refresh JWT。

- 凭证由 `admin` 通过 `/auth/service-tokens` 创建/列出/撤销；租户只取自 JWT，请求体不接受 `tenant_id`。
- 原始 token 形如 `pmgate_<随机值>`，只在创建响应中返回一次；数据库 `service_tokens` 只存 SHA-256，不存明文或可逆哈希。
- 默认有效期 90 天（创建时 1–365 天），可随时撤销；撤销或到期后认证失败。
- scope 固定为 `release_gate:read`，不能审批、不能写会话、不能读取会话正文。
- 门禁端点绕过 72 小时上下文缓存，直接 `session_store.load()` 读取存储，避免失效审批被旧缓存放行。
- 跨租户或会话不存在统一返回 404；凭证无效/撤销/过期返回 401；scope 不允许返回 403；计算或审计写入失败返回 503 + `decision=block` + `gate_unavailable`（fail-closed）。
- 每次通过认证的检查写入 append-only `release_gate_checks`（decision / reason_code / approval_status / approval_id / evaluation_version_digest / evidence_digest / release_batch_id）；写入失败不得返回 `allow`。
- 401/404 只记录 token hash 前缀、`token_id`、租户与会话 ID；绝不记录原始 token、token_hash 全文或审批备注。
- 门禁响应不含会话正文、用户材料、审批备注或人工判定依据，并设置 `Cache-Control: no-store`。

### Multi-Tenant Isolation

会话、审计事件、人工动作等核心记录都带 `tenant_id`，查询按当前认证用户的租户范围过滤。

读取路径为 fail-closed：`get_current_tenant` 对空 `tenant_id` 令牌直接返回 403；存储层的 `load`、`list_sessions`、`session_exists`、`list_projection` 在空租户下抛 `TenantIsolationError`（PostgreSQL 与 SQLite 一致）。跨租户读取只能显式传入 `SYSTEM_ACCESS` 内部哨兵，且每次使用都会写 warning 审计日志。

这属于面向本地/小团队场景的行级隔离，不是企业级强隔离方案。

### Rate Limiting

限流基于 `slowapi`：PostgreSQL/full 模式使用 Redis 计数，SQLite/demo/lite 模式使用进程内 `memory://` 计数器。内存计数器不跨进程共享，只适合本地演示。

当前文档主线中已确认的限制包括：

| Endpoint | Limit |
|----------|-------|
| `POST /auth/login` | 10 requests / minute |
| `POST /auth/register` | 5 requests / hour |
| `POST /chat/*` | 30 requests / hour |
| Stage advance endpoints | 20 requests / hour |

### Reverse Proxy and TLS

生产 compose 使用 Nginx 作为统一入口，当前暴露：
- `80:80`
- `443:443`

Nginx 配置来自：
- `nginx/nginx.conf`
- `nginx/conf.d/app.conf`
- `nginx/certs/`

因此当前仓库并不是“只提供 HTTP”。它提供的是：
- 可工作的本地 HTTPS / TLS 入口
- 默认使用自签名证书

这意味着：
- `curl -k https://localhost/...` 是当前推荐验证方式
- 浏览器会对自签名证书给出警告
- 若要公网部署，仍应替换为 CA 签发证书

### Secrets Management

`docker-compose.yml` 挂载以下文件型 secrets：
- `jwt_secret`
- `postgres_password`
- `redis_password`
- `deepseek_api_key`
- `tavily_api_key`
- `grafana_password`

`scripts/gen_secrets.sh` 会把 JWT、PostgreSQL、Redis 三项同时同步到 `.env`，因为应用环境变量优先级高于 `/run/secrets`；Grafana 密码只读 secret，API key 的 `.env` 占位行会被注释以便读取 secret。因而不能笼统宣称完整栈完全不在 `.env` 保存敏感值。`.env.demo` 仍是脱敏离线模板，不包含真实 API Key、数据库密码或证书私钥。

前端镜像隔离：`frontend` 服务使用 `Dockerfile.frontend`，只安装 PEP 735 `frontend` 依赖组（Streamlit / Altair / pandas / requests / python-dotenv），镜像内不含 `api/`、`core/`、`storage/` 等后端源码与数据库驱动。compose 中 frontend 不挂载任何 secret、不读取 `.env`、也不注入 `POSTGRES_HOST`/`REDIS_HOST`，运行时只接收 `API_BASE`（及演示开关）。该边界由 `tests/test_frontend_image_isolation.py` 固化。

### Additional Hardening Already Present

| Item | Current behavior |
|------|------------------|
| JWT secret validation | 启动时校验长度，短密钥直接报错 |
| CORS restriction | 默认限制为 `https://localhost`，不是 `*` |
| Redis auth | `--requirepass` + healthcheck 认证 |
| Resource limits | Compose 中设置 `deploy.resources.limits` |
| Restart policy | `restart: unless-stopped` |
| Structured logs | 应用日志为 JSON 输出 |

### Data Security（数据分级 / 字段加密 / PII 掩码）

Phase 1（T1.1–T1.4，自 v1.0.3 起落地并沿用至今）的数据安全能力，完整设计见 [data-classification-and-privacy.md](data-classification-and-privacy.md)：

| 能力 | 实现 | 位置 |
|------|------|------|
| 数据分类分级 | `ProjectContext` 落库数据打三级标签（公开示例 / 客户业务材料 / 敏感个人信息），支持覆写并留审计 | `core/models.py` `data_classification` 字段；`PATCH /sessions/{id}/data-classification` |
| 字段级加密 | 存储层 Fernet 对称加密，密文带 `enc:v1:` 前缀；覆盖 `research_target` / `goal` / `user_materials` / 用户材料型 evidence summary+claims / conversation content / pending actions / report content。`make setup` / `scripts/gen_secrets.sh` 会生成 `secrets/data_encryption_key` 并以 Docker secrets 注入；PostgreSQL 后端或 `APP_ENV=production` 下缺失/错误密钥必须 `FieldDecryptionError` fail-closed，不会静默返回明文 | `storage/field_security.py`；`/health.data_encryption` |
| 事件/审计脱敏 | `session_events` 与 `audit_events` 的自由文本字段按分级改写为 `{"_redacted": true, "sha256": ..., "length": ...}`；用户消息只记录 `input_sha256` / `input_length` / state，不落原文；`public_demo` 保持可读 | `core/data_protection.py`；`core/audit_service.py`；`core/session_service.py` |
| PII 掩码 | 聊天正文在 `send_message` 进入模型前、补充材料在加入时做四类正则检测；命中升级为 `sensitive_personal` 并强制出站掩码。`PII_MASK_BEFORE_LLM` 仅对仍为 `business_internal` / `public_demo` 的内容保留开关语义 | `tools/safety_classifier.py`（`PII_PATTERNS` / `scan_user_message_pii`）；`core/llm/outbound_guard.py`；`core/evidence_service.py` |
| 中断 checkpoint | `langgraph_interrupt` + PostgreSQL 使用独立 Fernet key 加密完整 `ProjectContext` checkpoint；要求持久 PostgreSQL 后端、单 worker，并在初始化或健康异常时 fail closed。SQLite 的 memory checkpoint 仅供本地调试且进程重启即丢失 | `graph/checkpoint_manager.py`；Alembic V006/V007；`/health/ready` |
| AI 生成标识 | 报告导出首屏中文免责声明，对齐《生成合成内容标识办法》 | `core/report_service.py` |

### Identity, Workspace and Approval Integrity（v1.7.0）

- **工作区邀请**：`workspace_invitations` 只存 token 的 SHA-256；原始 token 仅在创建响应返回一次，默认 7 天有效。接受邀请在同一事务内校验 pending/未过期/邮箱未注册并创建同租户成员。
- **刷新令牌**：`/auth/refresh` 不再信任旧 refresh token 内的 role，而是按 `sub` 重新读取当前用户记录并签发当前角色；用户不存在或角色非法时返回 401。
- **复核身份**：上线批准、风险处置、专家复核与 EvalRun 人工校准的复核人固定取 JWT `user_id`，请求体不再接受 `reviewer_id`。
- **发布授权**：`ProjectApproval.evidence_digest` 绑定批准时的测试运行（含实际输出摘要）、人工校准（含判定依据摘要与复核人）、处置复核、安全发现与阻断动作快照；任一证据变化使 `effective_status` 变为 `invalidated`，历史记录保留但不复活。
- **测试可信度**：上线证据要求 `execution_kind=real_target_execution`、`execution_outcome=success`、`judge_result=passed`、`judge_mode=human`，并存在带非空 `human_comment` 的 `human_label=passed` 人工校准；同一已完成 `target_http` 评估批次必须覆盖全部必测用例。HTTP 500 / timeout / 契约错误不可通过人工改判成为成功证据。

### Workflow State Fail-Closed

未知或非法 `current_state` 不允许自动回退到 `INIT`：

- 运行路径：`graph.runner.run_one_step` 与 `core.execution_service.execute_one_turn` 在进入节点前调用 `assert_advanceable`；未知状态由 `mark_invalid_state` 改写为 `RECOVERY_REQUIRED` 并写 `workflow_state_invalid` 审计事件，不执行任何节点。
- 存储路径：`storage/backends/postgres.py` 与 `sqlite_store.py` 的 `load()` 先经 `sanitize_persisted_state`，把旧版本或人工改库留下的未知状态改写为 `RECOVERY_REQUIRED` 并保留原始值到 `last_error`，避免 Pydantic 校验失败表现为 500/404。
- 阻断态：`ERROR` / `RECOVERY_REQUIRED` 下 `send_message` 抛 `WorkflowBlockedError`，API 返回 409；只能通过 `POST /sessions/{session_id}/workflow/recover` 显式恢复，目标状态必须属于可恢复集合且恢复动作写 `workflow_recovered` 审计事件。
- 确定性：判定只依赖当前状态值，不调用 LLM、不读取外部服务。

### Production Safety Gate

CI 的 `production-safety` job 为 blocking，覆盖：Alembic V008→动态 head（当前 V013）升级/回滚、production safety 测试集（状态 fail-closed、HIGH/CRITICAL 阻断、事件脱敏、字段加密、retention 租户边界、ID 唯一性、发布门禁凭证/审计存储）以及 PostgreSQL + Redis 业务 E2E。job 设置 `PRODUCTION_SAFETY_REQUIRED=1`，缺少数据库、Redis 或加密密钥时测试失败而不是跳过。

### What This Deployment Still Does NOT Provide

- 面向公网的完整安全基线
- 企业级租户隔离
- 外部 SIEM / 审计日志汇聚
- 专业 secrets manager 集成（如 Vault / KMS）
- 非 Docker 部署的字段加密密钥自动生成与托管（Docker 部署由 `make setup` 生成；裸机部署需运维者在 `.env` 显式设置 `DATA_ENCRYPTION_KEY`）
- checkpoint 密钥自动生成、托管或轮换（启用 PostgreSQL 中断模式时，运维者须另行配置并备份 `CHECKPOINT_ENCRYPTION_KEY`，且不得复用 `DATA_ENCRYPTION_KEY`）
- Streamlit 端的完整登录门户界面

当前前端更像内部工作台，认证能力主要在 API 层完成。

---

## Part 2: Workflow Safety Layer

### SafetyFinding Types

当前核心安全发现类型（`core/models.py` 中 `SafetyFinding.risk_type` 的权威枚举，共 10 项）：

- `prompt_injection`
- `sensitive_info`
- `unsupported_claim`
- `over_autonomy`
- `unsafe_instruction`
- `source_untrusted`
- `policy_gap`
- `improper_output_handling` —— OWASP LLM05 Improper Output Handling（T2.1 新增）
- `system_prompt_leakage` —— OWASP LLM07 System Prompt Leakage（T2.1 新增）
- `unbounded_consumption` —— OWASP LLM10 Unbounded Consumption（T2.1 新增）

### Blocking Behavior

高风险或关键风险的安全发现、证据缺口、评测失败、解析错误等，会通过 Review Gate / Stage Gate 进入阻断态，并生成 `PendingHumanAction`。

这套机制和基础设施安全是分开的：
- 前者约束“AI 输出能否推进”
- 后者约束“系统访问和部署是否受控”

### Current Limits

- 规则设计仍偏轻量、确定性
- 这不是完整的生产级安全策略引擎
- `unsupported_claim` 依赖证据引用和规则判断，不等于事实核验系统
- `policy_gap` 仍以高风险节点和触发方式的人工审核要求为主
- `core/report_service.py` 的 **Markdown 导出已做输出净化**（2026-09-01：`_sanitize_markdown` 转义 HTML 字符并中和伪协议链接，见 `risk-taxonomy-engine.md` §3.3）；**JSON 导出（`content_json`）不做净化**：下游消费侧若直接将 JSON 内容渲染为 HTML，输出净化责任仍在消费端。

因此，当前 workflow safety 能证明“系统会阻断明显高风险推进”，但不能替代正式安全评审。
