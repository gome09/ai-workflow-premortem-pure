# AI Workflow Pre-mortem & Human Oversight Platform

> **Second Public Edition** — This is the second public edition of this repository. The first edition remains in its separate repository and is not affected. This release is local-preview only: suitable for personal use and trusted small-team internal preview, **not** for production, SaaS, or public-internet deployment. See [SECOND_EDITION.md](SECOND_EDITION.md) for details.

> **Current release:** `v0.8.0-beta.1-local-preview-final`
> Status: v0.8.0-alpha.11 — Full Acceptance: PASS (2026-05-30)
>
> Acceptance scripts: 13/13 PASS, 707/707 checks. Pytest: 148/148 passed. OpenAPI: 66,931 bytes, 61 paths.
>
> **Real E2E validation (2026-05-30 ~ 2026-05-31):**
> - Low-risk room booking E2E: **PASS** — Stage 0–4 complete, report creation 200, real DeepSeek + Tavily
> - Low-risk reading planner E2E: **PASS** — Stage 0–4 complete with real DeepSeek + Tavily
> - Student management E2E: **EXPECTED_SAFETY_BLOCK_CONFIRMED** — HIGH-risk gate blocked as expected
> - Critical-risk medication mgmt E2E: **SAFETY_BLOCKED** — Stage 3 correctly blocked for critical-risk medical scenario
> - Risk-adaptive Stage 3 gate: **implemented and validated** (26/26 tests, 3 smokes PASS)
> - Bugs fixed: EvidenceSource unhashable, report export IndexError, large-session report JSONB/OOM
>
> **Ready for:** personal local use, 2–5 person small-team internal use, AI project pre-mortem, failure mode analysis, human oversight workflow design, EvalCase draft generation, local report export.
>
> **NOT ready for:** production SaaS, public internet deployment, multi-tenant enterprise use, unsupervised automated decisions.
>
> Evidence: [artifacts/full_acceptance_latest_minimal/](artifacts/full_acceptance_latest_minimal/)
> E2E results: [docs/e2e-results-summary.md](docs/e2e-results-summary.md)
> Project state & constraints: [CLAUDE.md](CLAUDE.md) | [docs/current_project_state.md](docs/current_project_state.md)

---

## Version / Release Clarification

| Item | Value |
|------|-------|
| Source package version | `0.8.0-alpha.11` |
| Current release / acceptance label | `v0.8.0-beta.1-local-preview-final` |
| Accepted usage scope | Personal and trusted small-team local preview |
| Production status | **NOT production-ready** |

The source package version and release/acceptance label are intentionally different. The code package remains `0.8.0-alpha.11`; the local-preview acceptance state is tracked by `v0.8.0-beta.1-local-preview-final`.


## Full Acceptance Summary

| Phase | Result |
|-------|--------|
| Docker environment | postgres healthy, redis healthy |
| ruff check / format | PASS |
| compileall / version_check | PASS (0.8.0-alpha.11) |
| Acceptance scripts (13 scripts, 707 checks) | PASS |
| Full pytest (148 tests) | PASS, 0 failures |
| API /health | ok |
| OpenAPI | 66,931 bytes, 61 paths |
| Frontend container | running, logs clean |
| Runtime logs | no Traceback / ImportError / ValidationError / RuntimeError |
| **Overall** | **PASS** |

**Validated with real API keys (2026-05-30 ~ 2026-05-31):**
- Real DeepSeek API: ✅ PASS (low-risk E2E)
- Real Tavily API: ✅ PASS (low-risk E2E)
- Low-risk room booking E2E: ✅ PASS (Stage 0–4 complete, report creation 200)
- Low-risk reading planner E2E: ✅ PASS (Stage 0–4 complete)
- Student management E2E: ✅ EXPECTED_SAFETY_BLOCK_CONFIRMED (HIGH-risk gate blocked)
- Critical-risk medication mgmt E2E: ✅ SAFETY_BLOCKED (Stage 3 correctly blocked)

**Still not validated / out of scope for local-preview:**
- Report export through a real browser download flow — optional manual check
- Production auth / RBAC — architectural limitation, target v1.0
- Multi-tenant isolation — out of scope
- Public internet deployment — out of scope
- Load / concurrency testing — out of scope for local-preview

---

## What This Project Does

本项目不是 Dify / Flowise / Langflow 的替代品，也不是通用 Agent Builder。它面向 AI 项目立项阶段，通过四个阶段的对话式引导，帮助你在项目立项时系统性地分析 AI 模型风险。

| 能力 | 说明 |
|------|------|
| 失败模式识别 | Stage 1: 搜索 + DeepSeek V4 Pro thinking 分析，识别项目潜在失败模式 |
| 人机协同工作流设计 | Stage 2: DeepSeek V4 Flash non-thinking 设计 Human-in-the-loop 工作流 |
| Zero-Shot 压力测试 | Stage 3: DeepSeek V4 Pro thinking 生成 EvalCase，评估模型边界 |
| 触发方式与执行建议 | Stage 4: DeepSeek V4 Flash non-thinking 生成部署与触发策略 |
| 人机监督 (Human Oversight) | PendingHumanAction 审核闭环：escalate / edit / evidence / parser |
| 审核关卡 (Review Gate) | Transition Policy + Stage Gate 阻断未解决的 blocker |
| 证据核验 (Evidence) | EvidenceSource 采集、核验、门禁检查 |
| 安全发现 (Safety) | SafetyFinding + Prompt Injection Scanner + Risk Taxonomy |
| Eval 覆盖率 | EvalCase 覆盖门禁 + EvalRun 评分 + 人工评审 |
| 报告导出 | JSON / Markdown ReportArtifact，含 readiness 与 governance 摘要 |
| 审计追踪 | 完整审计事件记录 + Streamlit Audit Workbench 可视化 |

---

## 技术栈

| 层 | 技术 |
|----|------|
| API | FastAPI (Python 3.11+) |
| 前端 | Streamlit Review Workbench |
| 状态机 | LangGraph (single_step 默认；langgraph_interrupt 可选实验) |
| LLM | DeepSeek V4 Pro / V4 Flash (兼容 OpenAI Chat Completions 接口) |
| 搜索 | Tavily Search API |
| 数据库 | PostgreSQL (session persistence, langgraph checkpoints) |
| 缓存 | Redis |
| 依赖管理 | uv / pip |
| 容器化 | Docker Compose |

---

## Quick Start


### Security boundary for personal use

Use this build only on localhost or a trusted private network. Do not expose it directly to the public internet. Keep `.env` out of version control, use strong local database passwords, and review all AI-generated outputs before acting on them.

### Docker (Recommended)

```bash
# 1. Copy and configure environment
cp .env.example .env
# Edit .env — fill in DEEPSEEK_API_KEY, TAVILY_API_KEY, POSTGRES_PASSWORD

# 2. Start all services
docker compose up -d

# 3. Verify API
curl http://localhost:8000/health

# 4. Open frontend
# http://localhost:8501
```

### Local Development (without Docker)

```bash
# 1. Install dependencies
uv sync --all-extras

# 2. Configure environment
cp .env.example .env
# Edit .env with your keys

# 3. Start PostgreSQL and Redis
docker compose up postgres redis -d

# 4. Start API
uv run uvicorn api.main:app --reload --port 8000

# 5. Start Streamlit
uv run streamlit run frontend/app.py --server.port 8501
```

For detailed setup instructions, see [docs/local_setup.md](docs/local_setup.md).
For startup guide, see [docs/startup.md](docs/startup.md).

---

## Environment Variables

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `DEEPSEEK_API_KEY` | 是 | — | DeepSeek API 密钥 |
| `DEEPSEEK_BASE_URL` | 否 | `https://api.deepseek.com` | DeepSeek API 地址 |
| `MODEL_STAGE_1` | 否 | `deepseek-v4-pro` | Stage 1 模型 |
| `MODEL_STAGE_2` | 否 | `deepseek-v4-flash` | Stage 2 / INIT 模型 |
| `MODEL_STAGE_3` | 否 | `deepseek-v4-pro` | Stage 3 模型 |
| `MODEL_STAGE_4` | 否 | `deepseek-v4-flash` | Stage 4 模型 |
| `MODEL_STAGE_1_THINKING` | 否 | `enabled` | Stage 1 thinking mode |
| `MODEL_STAGE_2_THINKING` | 否 | `disabled` | Stage 2 / INIT thinking mode |
| `MODEL_STAGE_3_THINKING` | 否 | `enabled` | Stage 3 thinking mode |
| `MODEL_STAGE_4_THINKING` | 否 | `disabled` | Stage 4 thinking mode |
| `DEEPSEEK_REASONING_EFFORT` | 否 | `high` | V4 thinking 推理强度 |
| `TAVILY_API_KEY` | 是 | — | Tavily 搜索 API 密钥 |
| `POSTGRES_HOST` | 否 | `localhost` | PostgreSQL 主机 |
| `POSTGRES_PORT` | 否 | `5432` | PostgreSQL 端口 |
| `POSTGRES_DB` | 否 | `ai_workflow` | 数据库名 |
| `POSTGRES_USER` | 否 | `postgres` | 数据库用户 |
| `POSTGRES_PASSWORD` | 是 | — | 数据库密码 |
| `REDIS_HOST` | 否 | `localhost` | Redis 主机 |
| `REDIS_PORT` | 否 | `6379` | Redis 端口 |
| `REDIS_PASSWORD` | 否 | — | Redis 密码 |
| `REDIS_DB` | 否 | `0` | Redis DB |
| `APP_ENV` | 否 | `development` | 环境 |
| `LOG_LEVEL` | 否 | `INFO` | 日志级别 |
| `SESSION_TTL_HOURS` | 否 | `72` | 会话保留时长 |
| `API_BASE` | 否 | `http://localhost:8000` | 前端访问 API 地址 |
| `STAGE_OUTPUT_MODE` | 否 | `json_first` | Stage 输出模式 |
| `WORKFLOW_EXECUTION_MODE` | 否 | `single_step` | 执行模式 |

---

## 默认执行模式

```bash
WORKFLOW_EXECUTION_MODE=single_step
```

`single_step` 是稳定的默认模式。每次 `/chat/{id}` 调用推进工作流一个确定步骤。`PendingHumanAction` 记录是权威的业务阻断器。Review Gate 和 Stage Gate 在所有阻断器解决前阻止阶段推进。

### Optional: LangGraph Interrupt（实验性）

```bash
WORKFLOW_EXECUTION_MODE=langgraph_interrupt
```

实验性的 checkpoint/interrupt 模式。未经过生产并发或故障场景测试。

---

## 目录结构

```text
ai-workflow-tool/
├── api/                    # FastAPI 应用与路由
│   ├── main.py             #   入口、/health
│   ├── schemas.py          #   Pydantic 模型
│   └── routers/            #   chat, session, stage, oversight, evidence,
│                           #   safety, eval, reports, interrupts
├── core/                   # 核心业务服务
│   ├── config.py           #   环境变量配置
│   ├── models.py           #   领域模型 (ProjectContext, Session, etc.)
│   ├── execution_mode.py   #   single_step / langgraph_interrupt
│   ├── execution_service.py / session_service.py / oversight_service.py
│   ├── stage_readiness_service.py / stage_advancement_contract.py
│   ├── stage_resolution_service.py / stage_operation_service.py
│   ├── stage_revision_service.py / stage_scope_service.py
│   ├── evidence_service.py / safety_service.py
│   ├── eval_service.py / eval_runner.py / eval_judge.py
│   ├── report_service.py / report_diff.py / audit_service.py
│   └── reviewed_output_service.py / context_manager.py
├── stages/                 # 四个阶段的执行逻辑与 Prompt
│   ├── stage_1_failure_mode.py / stage_2_workflow_design.py
│   ├── stage_3_stress_test.py / stage_4_trigger.py
│   ├── prompts.py / json_prompts.py
│   └── schemas.py / validators.py / base.py / raw_output_guard.py
├── graph/                  # 阶段状态机
│   ├── runner.py           #   single_step runner (默认)
│   ├── langgraph_interrupt_runner.py  # 实验性 interrupt runner
│   ├── transition_policy.py / review_gate.py / interrupt_gate.py
│   └── nodes.py / builder.py / edges.py / interrupts.py
├── tools/                  # 搜索、证据、安全工具
│   ├── search.py / evidence_filters.py / evidence_ranker.py
│   ├── safety_classifier.py / prompt_injection_scanner.py
│   ├── risk_taxonomy.py / flag_extractor.py
│   └── source_classifier.py / material_parser.py
├── storage/                # PostgreSQL + Redis 存储层
│   ├── session_store.py
│   └── cache.py
├── frontend/               # Streamlit Review Workbench
│   ├── app.py / api_client.py / state.py
│   └── components/         #   action_queue, audit_timeline, eval_panel,
│                           #   evidence_panel, report_panel, safety_panel
├── tests/                  # 测试套件 (148 tests)
├── docs/                   # 架构、安全、阶段推进文档
│   └── acceptance/         #   验收记录与 closure summary
├── scripts/
│   ├── acceptance/         #   AC-09 ~ AC-11 验收脚本
│   │   └── archived/       #   AC-05 ~ AC-08 历史探针
│   └── version_check.py
├── examples/               # 示例输入与场景数据
├── .env.example            # 环境变量模板
├── pyproject.toml          # Python 项目配置
├── Makefile                # 开发快捷命令
├── Dockerfile / docker-compose.yml
├── CHANGELOG.md / ROADMAP.md / LICENSE / SECURITY.md
└── CONTRIBUTING.md
```

---

## 主要 API 接口

```text
GET  /health                                      # 健康检查、版本和执行模式

POST /sessions/                                   # 创建新会话
GET  /sessions/                                   # 列出历史会话
GET  /sessions/{id}                               # 获取会话详情

POST /chat/{id}                                   # 发送消息并推进一个执行回合

POST /sessions/{id}/materials                    # 追加用户材料并生成证据源
POST /sessions/{id}/flags/resolve                 # 处理需核验 flag
GET  /sessions/{id}/export                        # 导出 json / markdown 报告

GET  /sessions/{id}/stage-readiness               # 查看全部阶段 readiness
GET  /sessions/{id}/stage-readiness/{stage_id}    # 查看单阶段 readiness
GET  /sessions/{id}/stage-gate/{stage_id}         # 查看权威阶段 gate
GET  /sessions/{id}/stage-resolution              # 查看全部阶段下一步操作
GET  /sessions/{id}/stage-resolution/{stage_id}   # 查看单阶段下一步操作

POST /sessions/{id}/stages/{stage_id}/rerun       # 准备重跑阶段
POST /sessions/{id}/stages/{stage_id}/revise      # 提交阶段修订
POST /sessions/{id}/stages/{stage_id}/rollback    # 回退阶段
POST /sessions/{id}/stages/{stage_id}/sync-review-actions

GET  /sessions/{id}/actions                       # 列出人工动作
GET  /sessions/{id}/actions/{action_id}           # 查看单个人工动作
POST /sessions/{id}/actions/{action_id}/resolve   # 处理人工动作
GET  /sessions/{id}/audit-events                  # 查看审计事件

GET  /sessions/{id}/evidence                      # 查看证据
GET  /sessions/{id}/evidence/{evidence_id}        # 查看单条证据
POST /sessions/{id}/evidence/{evidence_id}/verify # 核验证据

GET  /sessions/{id}/safety-findings               # 查看安全发现
POST /sessions/{id}/safety-findings/{finding_id}/resolve

GET  /sessions/{id}/eval-cases                    # 查看 EvalCase
GET  /sessions/{id}/eval-runs                     # 查看 EvalRun
POST /sessions/{id}/eval-cases/run                # 批量 EvalRun
POST /sessions/{id}/eval-cases/{eval_id}/run      # 单条 EvalRun
POST /sessions/{id}/eval-cases/{eval_id}/score    # 记录评分

POST /sessions/{id}/reports                       # 创建报告 artifact
GET  /sessions/{id}/reports                       # 列出报告 artifact
GET  /sessions/{id}/reports/{report_id}           # 查看单个报告 artifact

GET  /sessions/{id}/interrupt-records             # 查看 interrupt records
GET  /sessions/{id}/interrupt-records/{interrupt_id}
```

---

## Testing

```bash
# Core test suite
uv run pytest tests/ -q

# Verbose output
uv run pytest tests/ -v

# Single file example
uv run pytest tests/test_models.py -v
```

- Tests use in-memory storage and monkeypatched LLM behavior.
- Tests do not require real DeepSeek, Tavily, PostgreSQL, Redis, or network access.

---

## Known Limitations

1. **Local-preview only**: This is NOT a production release. No authentication, no authorization, no multi-tenant isolation.
2. **No production auth / RBAC**: API endpoints are open. Not suitable for public deployment.
3. **Single-user review workbench**: Streamlit Review Workbench is for controlled single-operator review.
4. **PostgreSQL required for full API startup**: Tests use in-memory storage, but full API runtime requires PostgreSQL.
5. **Real DeepSeek / Tavily validated**: Real E2E completed with live keys (low-risk room booking PASS, low-risk reading planner PASS, student management HIGH-risk SAFETY_BLOCKED as expected, critical-risk medication SAFETY_BLOCKED as expected).
6. **LangGraph interrupt mode is experimental**: Default is `single_step`; interrupt mode is preserved for experimentation.
7. **No production deployment hardening**: No rate limiting, secrets management, or production observability.

---

## Key Documentation

| Document | Purpose |
|----------|---------|
| [docs/current_project_state.md](docs/current_project_state.md) | **Authoritative project status** |
| [CLAUDE.md](CLAUDE.md) | Constraints for Claude Code sessions |
| [docs/validation-status.md](docs/validation-status.md) | Current validation status summary |
| [docs/e2e-results-summary.md](docs/e2e-results-summary.md) | Real E2E results summary |
| [docs/stage3-risk-adaptive-gate.md](docs/stage3-risk-adaptive-gate.md) | Risk-adaptive Stage 3 gate |
| [docs/startup.md](docs/startup.md) | Startup instructions |
| [docs/local_setup.md](docs/local_setup.md) | Environment setup guide |
| [docs/acceptance/docker_final_acceptance_report.md](docs/acceptance/docker_final_acceptance_report.md) | Latest acceptance report |
| [LIVE_E2E_LOW_RISK_READING_PLANNER_REPORT.md](LIVE_E2E_LOW_RISK_READING_PLANNER_REPORT.md) | Low-risk E2E report |
| [LIVE_E2E_MEDICATION_MANAGEMENT_REPORT.md](LIVE_E2E_MEDICATION_MANAGEMENT_REPORT.md) | Critical-risk E2E report |
| [CHANGELOG.md](CHANGELOG.md) | Version history |
| [ROADMAP.md](ROADMAP.md) | Development roadmap |
| [docs/architecture.md](docs/architecture.md) | Architecture overview |
| [docs/security-model.md](docs/security-model.md) | Security model |

---

## License

MIT
