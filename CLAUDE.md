# CLAUDE.md

本文件是 Claude Code 在本仓库的**补充**指导，只承载 [AGENTS.md](AGENTS.md) 未覆盖的内容。

**仓库级规则、当前事实基线、常用命令、架构不变量、安全与合规边界一律以 [AGENTS.md](AGENTS.md) 为准。** 本文件刻意不重复这些内容——此前两份文件并行维护同一组可漂移事实，已导致过同一个错误数字被同步写进两处。如两者冲突，优先遵守 AGENTS.md 和最新 `.upgrade/STATE.md`。

## 项目概述

AI 工作流预验尸与人机监督平台。项目源于本科毕业设计，当前按长期维护的开源项目演进。系统在 AI 项目立项阶段通过四阶段分析（失败模式识别 → 人机协同工作流设计 → Zero-Shot 压力测试 → 触发策略生成），结合 LOW/MEDIUM/HIGH/CRITICAL 风险自适应门禁与人工监督，系统性发现部署前风险。详见 [README.md](README.md) 与 [docs/spec/architecture.md](docs/spec/architecture.md)。

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

## 代码规范细则

- Ruff：`line-length=100`，`target-version=py311`，规则集 `E,F,I,UP,S`（`E501` 忽略）。提交前跑 `make lint`。
- pytest：约定 `test_*.py` / `Test*` / `test_*`，测试目录固定 `tests/`，`asyncio_mode = "auto"`。单元测试主要使用内存存储与 monkeypatched LLM；全流程验证优先使用 Mock 模式（`.env.demo`）。
- 测试基线必须用 `uv run pytest` / `make test` 录制。用系统 Python 直接跑会因缺主依赖产生虚假的 skip 计数。引用测试数字时必须附日期。

## docs/spec 状态清单

`docs/spec/` 存放系统设计规格，当前 8 份全部为 `Status: Implemented`：

architecture / api-reference / security-model / stage3-risk-adaptive-gate / supply-chain-security / data-classification-and-privacy / risk-taxonomy-engine / governance-platform

新增设计态规格用 `Status: Designed, not implemented` 标注，实现后必须更新 Status 行。规格中如有"已实现"但代码不支持的表述，按 AGENTS.md 的事实来源优先级以代码为准并更新规格。

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
