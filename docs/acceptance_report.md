# AI Workflow Pre-mortem 当前验收报告

> 本文件记录当前 v1.8.0 代码基线（2026-11-07）与回归摘要。v1.3.0（2026-10-31）基线与 v1.2.1 四阶段 E2E 快照、历史缺陷详录保留在下方历史章节；2026-07-18 四种启动方式的完整历史报告见 [`startup-methods-e2e-20260718.md`](../.upgrade/archive/reports/startup-methods-e2e-20260718.md)；v1.2.1 快照归档于 [`acceptance-history-v1.2.1.md`](archive/verification-reports/acceptance-history-v1.2.1.md)。

## 当前代码基线复核（2026-11-07）

本轮范围为「第三阶段发布门禁接入」；每项结果注明环境与范围，未执行项明确标注。

| 验证项 | 当前结果 |
|------|------|
| 版本一致性 | ✅ `core/version.py` = `pyproject.toml` = `1.8.0`（`version-check` 实测） |
| 全量测试 | ✅ `1219 passed, 6 skipped`（项目 `.venv` pytest，2026-11-07，`sqlite` + `memory` + `mock` + `single_step`，70.7s） |
| Skip 归因 | 6 个 skip：3 个 PostgreSQL/Redis E2E + 1 个 PG-only 存储模块 + 2 个 opt-in live provider 冒烟（仅 `LIVE_LLM_TESTS=1` 执行）；CI `production-safety` 设置 `PRODUCTION_SAFETY_REQUIRED=1` 时必须执行，离线 skip 不等于通过 |
| 既有业务闭环回归 | ✅ 审批/证据/处置/真实目标证据链测试全部通过；发布门禁复用既有判定，不改变审批规则 |
| Ruff / 格式 | ✅ `ruff check .` 通过；`ruff format --check .` 403 files already formatted |
| 类型检查 | ✅ mypy：205 source files，no issues（CI 仍为 non-blocking 观察期） |
| 文档一致性 | ✅ 37 份当前项目 Markdown，0 违规（`doc_consistency_check.py`） |
| 依赖审计 | ⚠️ 本地 `make audit` 实测 124 条 unique advisory / 19 个包（外部 advisory 库更新）；CI 已改为 non-blocking 观察步骤，不可修复项与分诊见 `.upgrade/STATE.md` Blockers |
| 数据库迁移链 | ✅ Alembic V001 → V013（V013：`service_tokens`、`release_gate_checks`；V012：`workspace_invitations`、`eval_cases.standard_version`、`eval_runs.case_version_digest` / `target_deployment_version`） |
| ProjectContext schema | ✅ `0.6.0-alpha.8` → `0.10.0`（`CURRENT_CONTEXT_SCHEMA_VERSION`） |
| 发布门禁 | ✅ `GET /release-gate/{session_id}` 只接受 service token；approved → `decision=allow`；未批准/rejected/stale/invalidated/public_demo/401/403/404/503 全部阻断；门禁绕过 72 小时缓存；每次检查写 `release_gate_checks`，审计写入失败 fail-closed |
| V008→V013 实测 | ⏳ 本轮新增 V013 迁移断言；CI `production-safety` 将执行 V008→V013→V008→V013。本地未连接真实 PostgreSQL，不宣称本地通过 |
| 远端 CI（上一轮） | ✅ 代码提交 `3316bb5` / run 41298061928 与文档提交 `93b9b71` / run 41298329901 的四个 job 全部 success，两次 CodeQL 均 success；本轮发布门禁改动尚未提交，CI 结果需在提交后以实际 run 为准 |
| 旧库租户归属 | ⚠️ 旧库 20 个会话与 90 条 `human_actions` 的 `tenant_id` 为 NULL（早于多租户模型），默认租户作用域查询不可见，需按实际归属回填。回填通道：`scripts/backfill_session_tenants.py`（默认 dry-run，仅填 `tenant_id IS NULL` 行） |

## 历史基线（2026-10-31，v1.3.0）

本节保留 v1.3.0 时期的工作区复核结果，不代表当前版本基线。

| 验证项 | 当时结果 |
|------|------|
| 版本一致性 | ✅ `core/version.py` = `pyproject.toml` = 1.3.0 |
| 全量测试 | `800 passed, 1 skipped`（项目 `.venv` pytest，2026-10-31，`sqlite` + `memory` + `mock`；包含会话工作台、治理真实数据隔离、稀疏趋势图、LangGraph checkpoint / durable resume 回归与前端 MVC 拆分后的契约测试） |
| LangGraph 中断实测 | ✅ PostgreSQL 加密 checkpoint 完成暂停 → runtime 重建 → 审批恢复 → checkpoint 清理；回滚至 `single_step` 再重新启用的两次 readiness 均为 HTTP 200 |
| 治理接口实测 | ✅ PostgreSQL 环境 `/governance/overview`、`/gate-trends`、`/actions-backlog` 均返回 HTTP 200；实测总览统计 2 个真实业务会话并隔离 2 个演示会话 |
| 前端实测 | ✅ Streamlit HTTP 200；治理页明确真实数据口径，柱状图显示横向参考网格，单周门禁数据使用固定 0%–100% 轴并提示不足以形成趋势线。2026-10-31 起前端按 MVC 分层（`models/` / `controllers/` / `views/`），`app.py` 仅入口装配，UI 行为不变 |
| 文档一致性检查 | ✅ 扫描 38 份当前项目 Markdown（排除 `.upgrade/`、archive、运行时产物和缓存），0 处违规（2026-10-31） |
| 数据库迁移链 | ✅ Alembic V001 → V008（V006：LangGraph checkpoint；V007：durable resume outbox；V008：租户索引、乐观锁与生成列） |
| V008 结构实测 | ✅ 临时 PostgreSQL 18 库上完成 `V007 → V008 → V007 → V008` 双向迁移；历史行生成列 / `tenant_id` 回填、`stage_id` 类型转换、NOT VALID 约束、租户索引命中与乐观锁并发行为均通过（2026-10-27）。真实业务库 `ai_workflow` 已按"备份 → 补齐 V001 基线缺失列 → `upgrade head`"路径升级到 V008，旧数据无损（20 会话 / 144 审计事件），备份保存在 `.upgrade/backup/` |
| ProjectContext 迁移链 | ✅ 0.6.0-alpha.8 → 0.7.0 → 0.8.0 → 0.9.0 |

## v1.3.0 回归验证（2026-07-17）

v1.3.0（formal-project-uplift Wave A–E）在 v1.2.1 基础上的变更不改动四阶段工作流执行路径；新增治理、类型检查、LLM Judge 和合规复核能力均按当前规格记录，LLM Judge 默认关闭。

| 验证项 | 结果 |
|------|------|
| 全量测试（Mock + SQLite 离线） | ✅ 650 passed, 1 skipped（2026-07-17 实测） |
| e2e-mock 场景验收 | ✅ 63 passed（2026-07-17 实测） |
| 版本一致性 | ✅ `core/version.py` = `pyproject.toml` = 1.3.0 |
| 四阶段全流程 E2E 会话 | 沿用 v1.2.1 历史快照；详见归档报告 |

## 历史报告入口

- [v1.2.1 验收与缺陷修复历史归档](archive/verification-reports/acceptance-history-v1.2.1.md)
- [2026-07-18 四种启动方式完整 E2E 报告](../.upgrade/archive/reports/startup-methods-e2e-20260718.md)

---

*当前报告最近更新：2026-11-07（v1.8.0 发布门禁接入轮；本地离线验证结果见最终答复）*
*当前架构版本：1.8.0*
*当前测试基线：`1219 passed, 6 skipped`（2026-11-07，SQLite + memory + mock + single_step）；历史数字仅作追溯。*
