# Security Model

> **Last updated:** 2026-07-14

This project has two security layers:

1. **Infrastructure security**: authentication, RBAC, tenant isolation, secrets, reverse proxy, rate limiting
2. **Workflow safety**: SafetyFinding, PendingHumanAction, Stage Gate, evidence and eval governance

---

## Part 1: Infrastructure Security

### Authentication

认证实现位于 `auth/`，API 采用 JWT Bearer Token。

| Token Type | Lifetime | Purpose |
|------------|----------|---------|
| Access token | 15 minutes | Authenticate API requests |
| Refresh token | 7 days | Obtain a new access token |

当前接口：
- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`

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

首个注册用户自动成为 `admin`，后续用户默认 `viewer`。

### Multi-Tenant Isolation

会话、审计事件、人工动作等核心记录都带 `tenant_id`，查询按当前认证用户的租户范围过滤。

这属于面向本地/小团队场景的行级隔离，不是企业级强隔离方案。

### Rate Limiting

限流基于 `slowapi`，计数依赖 Redis。

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

当前生产 compose 不再把敏感值主存放在 `.env`。

`docker-compose.yml` 使用 Docker secrets：
- `jwt_secret`
- `postgres_password`
- `redis_password`
- `deepseek_api_key`
- `tavily_api_key`
- `grafana_password`

`.env.example` 和 `.env.demo` 主要承载非敏感配置与本地演示配置。
其中 `.env.demo` 是脱敏离线模板，不包含真实 API Key、数据库密码或证书私钥。

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

Phase 1（v1.0.3，T1.1–T1.4）落地的数据安全能力，完整设计见 [data-classification-and-privacy.md](data-classification-and-privacy.md)：

| 能力 | 实现 | 位置 |
|------|------|------|
| 数据分类分级 | `ProjectContext` 落库数据打三级标签（公开示例 / 客户业务材料 / 敏感个人信息），支持覆写并留审计 | `core/models.py` `data_classification` 字段；`PATCH /sessions/{id}/data-classification` |
| 字段级加密 | 存储层对敏感字段做 Fernet 对称加密（可验证密文），密钥来自 `DATA_ENCRYPTION_KEY` | `storage/field_security.py` |
| PII 掩码 | LLM 调用前对材料做 PII 检测与掩码（`PII_MASK_BEFORE_LLM` 开关），命中产出 finding | `tools/safety_classifier.py`（`PII_PATTERNS`） |
| AI 生成标识 | 报告导出首屏中文免责声明，对齐《生成合成内容标识办法》 | `core/report_service.py` |

### What This Deployment Still Does NOT Provide

- 面向公网的完整安全基线
- 企业级租户隔离
- 外部 SIEM / 审计日志汇聚
- 专业 secrets manager 集成（如 Vault / KMS）
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

因此，当前 workflow safety 能证明“系统会阻断明显高风险推进”，但不能替代正式安全评审。
