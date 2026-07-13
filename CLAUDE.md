# CLAUDE.md

本文件为 Claude Code（及其他 AI 编码工具）在本仓库工作时的指导文件。

## 项目概述

AI 工作流预验尸与人机监督平台（本科毕业设计项目）。借鉴软件工程"预验尸"（Pre-mortem）方法论，在 AI 项目立项阶段通过四阶段引导式分析（失败模式识别 → 人机协同工作流设计 → Zero-Shot 压力测试 → 触发策略生成），结合风险自适应门禁（LOW/MEDIUM/HIGH/CRITICAL）系统性发现 AI 系统可能的失败模式。详见 [README.md](README.md) 与 [docs/architecture.md](docs/architecture.md)。

## 技术栈

FastAPI + LangGraph 状态机 + Streamlit 前端 + PostgreSQL/SQLite + Redis + JWT/RBAC 认证，容器化部署（Docker Compose + Nginx）。

## 常用命令

```bash
# 依赖安装
uv sync --all-extras

# 离线演示模式（无需 API Key / DB，推荐用于日常开发验证）
make demo-api      # 后端，自动使用 .env.demo
make demo-ui       # 前端

# 测试
make test          # 全量 pytest
make e2e-mock      # Mock 场景快速验收（~5秒）
make e2e-full-test # 全量测试（~8秒）

# Lint（ruff check + format --check，CI 强制）
make lint

# 版本一致性检查（pyproject.toml 与 core/version.py 对齐）
make version-check

# 本地 Postgres+Redis 全量开发
make dev-db && make dev-api && make dev-frontend

# Docker
make lite-up   # SQLite + Mock，零外部依赖
make setup && make prod-up   # 生产模式（PostgreSQL + Redis + 真实 LLM）
```

## 架构要点

- 工作流状态转换是**确定性的、代码控制的**——LLM 只负责生成分析内容，不自主决定流程跳转。
- 高风险决策必须走人工审核（`PendingHumanAction`）。
- Evidence / SafetyFinding / EvalCase / EvalRun / InterruptRecord / ReportArtifact 都是一等公民记录，不是附属数据。
- 请求执行路径：`SessionService` → `core.execution_service.execute_one_turn` → `graph.runner.run_one_step`（默认稳定路径 `single_step`；`langgraph_interrupt` 为实验性路径，仅在 `WORKFLOW_EXECUTION_MODE=langgraph_interrupt` 时启用）。
- 人工动作解决路径：`core.oversight_service.resolve_action` → `graph.transition_policy.evaluate_action_resolution` → `core.execution_service.sync_execution_after_action_resolution` → 门禁重新评估。
- `core/version.py` 是版本号唯一来源；`core/stage_readiness_service.py` 是阶段门禁权威判定源。
- 完整架构图与时序图见 [docs/architecture.md](docs/architecture.md)。

## 目录结构关键点

| 目录 | 说明 |
|---|---|
| `api/` | FastAPI 路由入口 `api/main.py` + `api/routers/` |
| `auth/` | JWT 认证 + RBAC + 多租户隔离 |
| `core/` | 核心业务服务；`core/gates/` 门禁引擎，`core/llm/` LLM 适配层（含 `mock_fixtures/`），`core/migrations/` 为 ProjectContext 数据 schema 迁移（区别于 `alembic/` 的数据库表结构迁移） |
| `stages/` | 四阶段执行逻辑，`stages/domain_profiles/` 领域提示词配置 |
| `graph/` | LangGraph 状态机 |
| `tools/taxonomies/` | 风险分类体系（NIST AI RMF / OWASP LLM Top 10 等） |
| `storage/backends/` | PostgreSQL / SQLite 存储实现 |
| `scenarios/manifests/` | 可插拔 Demo 场景定义 |
| `docs/` | 项目文档，索引见 [docs/README.md](docs/README.md) |
| `.upgrade/` | 升级工作区，见下方规则 |

## 代码规范

- Ruff：`line-length = 100`，`target-version = py311`，规则集 `E,F,I,UP`（`E501` 忽略）。提交前跑 `make lint`。
- 测试用 pytest，约定 `test_*.py` / `Test*` / `test_*`，测试目录固定在 `tests/`。
- 测试使用内存存储与 monkeypatched LLM，不依赖外部服务；跑全量流程验证需要 Mock 模式（`.env.demo`）。

## 文档维护

- 修改 `docs/` 下文档后请同步检查 [docs/README.md](docs/README.md) 索引是否需要更新条目。
- `docs/improvement-roadmap.md` 是持续维护的分阶段改进路线图（合规映射/企业工程/开源社区三条坐标轴），涉及安全或合规相关改动时应参照其差距清单。

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
