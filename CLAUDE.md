# CLAUDE.md

本文件是 Claude Code 在本仓库的补充指导。仓库级通用规则以 [AGENTS.md](AGENTS.md) 为准；如两者冲突，优先遵守 AGENTS.md 和最新 `.upgrade/STATE.md`。

## 项目概述

AI 工作流预验尸与人机监督平台。项目源于本科毕业设计，当前按长期维护的开源项目演进。系统在 AI 项目立项阶段通过四阶段分析（失败模式识别 → 人机协同工作流设计 → Zero-Shot 压力测试 → 触发策略生成），结合 LOW/MEDIUM/HIGH/CRITICAL 风险自适应门禁与人工监督，系统性发现部署前风险。详见 [README.md](README.md) 与 [docs/spec/architecture.md](docs/spec/architecture.md)。

当前事实基线：应用版本 `1.3.0`、Alembic head `V005`、ProjectContext schema `0.9.0`；最近一次本地全量测试为 `623 passed, 8 skipped`（2026-07-25）。Phase 0–4 已完成，`docs/plan/` 是历史计划，不是当前待办清单。

## 技术栈

FastAPI + LangGraph 状态机 + Streamlit 前端 + PostgreSQL/SQLite + Redis + JWT/RBAC 认证，容器化部署（Docker Compose + Nginx）。

## 常用命令

```bash
uv sync --all-extras          # 依赖安装

# 离线演示模式（无需 API Key / DB，推荐日常开发验证，自动用 .env.demo）
make demo-api                 # 后端 / make demo-ui  前端

make test                     # 全量 pytest
make e2e-mock                 # Mock 场景快速验收
make e2e-full-test            # 全量端到端
make lint                     # ruff check + format --check（CI 强制）
make typecheck                # mypy（本地应通过；CI 当前仍 non-blocking）
make doc-check                # 当前项目 Markdown 一致性检查（CI 强制）
make version-check            # 校验 pyproject.toml 与 core/version.py 对齐

make dev-db && make dev-api && make dev-frontend   # 本地 Postgres+Redis 全量开发

make lite-up                  # Docker：SQLite + Mock，零外部依赖
make setup && make prod-up    # Docker：生产模式（PostgreSQL + Redis + 真实 LLM）
```

完整栈注意：`make setup` 不生成 `DATA_ENCRYPTION_KEY`。生产环境需按 `.env.example` 生成 Fernet key 并在启动后确认 `/health.data_encryption` 为 `enabled`。

## 架构要点

- 工作流状态转换是**确定性的、代码控制的**——LLM 只生成分析内容，不自主决定流程跳转。
- 高风险决策必须走人工审核（`PendingHumanAction`）。
- `EvidenceSource` / `SafetyFinding` / `EvalCase` / `EvalRun` / `InterruptRecord` / `ReportArtifact` 是一等公民记录（均定义于 `core/models.py`），非附属数据。
- 请求执行路径：`SessionService` → `core.execution_service.execute_one_turn` → `graph.runner.run_one_step`。默认稳定路径 `single_step`；`langgraph_interrupt` 为实验路径，仅 `WORKFLOW_EXECUTION_MODE=langgraph_interrupt` 时启用。
- 人工动作解决路径：`core.oversight_service.resolve_action` → `graph.transition_policy.evaluate_action_resolution` → `core.execution_service.sync_execution_after_action_resolution` → 门禁重新评估。
- 版本权威源：`core/version.py` 与 `pyproject.toml` 必须一致；阶段门禁以 `core/stage_readiness_service.py` 和 `core/gates/` 为准。
- Alembic 负责数据库 schema；`core/migrations/` 只负责历史 ProjectContext JSON 迁移，当前版本为 0.9.0。

## 目录结构关键点

| 目录 | 说明 |
|---|---|
| `api/` | FastAPI 入口 `api/main.py` + `api/routers/` |
| `auth/` | JWT 认证 + RBAC + 多租户隔离 |
| `core/` | 核心业务；`gates/` 门禁引擎，`llm/` 适配层（`adapters/mock_fixtures/` 含 Mock 数据），`migrations/` 为 ProjectContext schema 迁移（区别于 `alembic/` 的数据库表迁移） |
| `stages/` | 四阶段执行逻辑，`domain_profiles/` 领域提示词 |
| `graph/` | LangGraph 状态机 |
| `tools/taxonomies/` | 风险分类体系（NIST AI RMF / OWASP LLM Top 10 等） |
| `storage/backends/` | PostgreSQL / SQLite 存储实现 |
| `scenarios/manifests/` | 可插拔 Demo 场景定义（JSON） |
| `docs/` | 项目文档，索引见 [docs/README.md](docs/README.md) |
| `.upgrade/` | 升级工作区；当前状态看 `STATE.md`，生命周期看 `MANIFEST.md` |

## 代码规范

- Ruff：`line-length=100`，`target-version=py311`，规则集 `E,F,I,UP,S`（`E501` 忽略）。提交前跑 `make lint`。
- pytest：约定 `test_*.py` / `Test*` / `test_*`，测试目录固定 `tests/`。单元测试主要使用内存存储与 monkeypatched LLM；全流程验证优先使用 Mock 模式（`.env.demo`）。测试数量会变化，引用数字时必须附日期。
- 开始修改前运行 `git status --short`；保留现有工作树改动，不格式化或覆盖任务范围外文件。
- 完成前至少运行与改动相称的测试，以及 `make doc-check`、`make version-check`、`git diff --check`。

## 文档维护

- 改动 `docs/` 后同步检查 [docs/README.md](docs/README.md) 索引。
- `docs/plan/improvement-roadmap.md` 与 phase-0~4 计划现在承担历史决策追溯职责；其中旧代码行号、旧迁移版本和未勾选项不代表当前状态。
- 当前状态以代码、`docs/spec/`、`.upgrade/STATE.md` 和最新 decisions 为准。不要继续在历史计划里维护当前待办；新的升级实施计划应写入 `.upgrade/plans/`。
- `docs/spec/` 存放系统设计规格，当前全部 `Status: Implemented`（architecture / api-reference / security-model / stage3-risk-adaptive-gate / supply-chain-security / data-classification-and-privacy / risk-taxonomy-engine / governance-platform）。新增设计态规格用 `Status: Designed, not implemented` 标注，实现后必须更新 Status 行。
- 字段加密属于“代码支持、部署条件启用”；留存天数属于“配置已暴露、自动清理未实现”。更新安全/合规文档时必须保留这两个边界。

<!-- project-upgrade:start -->
## Upgrade Workspace Rules

所有升级相关的临时文件、报告、分析、草稿必须放在 `.upgrade/` 目录。

### 禁止操作
- ❌ 不得在项目根目录创建升级相关临时文件
- ❌ 不得使用 `git add .`，必须显式 staging
- ❌ 不得删除 `.upgrade/` 外部文件（除非明确要求）
- ❌ 不得修改此受控块外的内容（除非明确要求）

### 必须操作
- ✅ 每次任务完成后更新 `.upgrade/STATE.md`
- ✅ 临时产物放入 `.upgrade/tmp/`
- ✅ 执行日志放入 `.upgrade/logs/`
- ✅ 重要决策记录到 `.upgrade/decisions/`
- ✅ 提交前运行 `git status --short` 检查改动
- ✅ 使用 `git add <specific-file>` 显式添加
<!-- project-upgrade:end -->
