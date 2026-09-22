# AI Workflow Pre-mortem 当前验收报告

> 本文件记录当前 v1.3.0 代码基线与回归摘要。v1.2.1 四阶段 E2E 快照、历史缺陷详录和原始统计已归档至 [`acceptance-history-v1.2.1.md`](archive/verification-reports/acceptance-history-v1.2.1.md)；2026-07-18 四种启动方式的完整历史报告见 [`startup-methods-e2e-20260718.md`](../.upgrade/archive/reports/startup-methods-e2e-20260718.md)。

## 当前代码基线复核（2026-09-21）

本节记录当前工作区的文档—代码一致性复核结果。

> 2026-07-25 一轮曾把 `623 passed, 8 skipped` 记为当前基线，该数字系用系统 Python 而非项目 `.venv` 运行所致（缺 `prometheus-fastapi-instrumentator` 触发 7 处 `importorskip`），已于 2026-07-31 更正。录制基线请统一使用 `uv run pytest` / `make test`。

| 验证项 | 当前结果 |
|------|------|
| 版本一致性 | ✅ `core/version.py` = `pyproject.toml` = 1.3.0 |
| 全量测试 | ✅ `731 passed, 1 skipped`（项目 `.venv` pytest，2026-09-21 实测；包含会话工作台、治理真实数据隔离、稀疏趋势图，以及 LangGraph checkpoint / durable resume 回归） |
| LangGraph 中断实测 | ✅ PostgreSQL 加密 checkpoint 完成暂停 → runtime 重建 → 审批恢复 → checkpoint 清理；回滚至 `single_step` 再重新启用的两次 readiness 均为 HTTP 200 |
| 治理接口实测 | ✅ PostgreSQL 环境 `/governance/overview`、`/gate-trends`、`/actions-backlog` 均返回 HTTP 200；实测总览统计 2 个真实业务会话并隔离 2 个演示会话 |
| 前端实测 | ✅ Streamlit HTTP 200；治理页明确真实数据口径，柱状图显示横向参考网格，单周门禁数据使用固定 0%–100% 轴并提示不足以形成趋势线 |
| 文档一致性检查 | ✅ 扫描 37 份当前项目 Markdown（排除 `.upgrade/`、archive、运行时产物和缓存），0 处违规（2026-09-21） |
| 数据库迁移链 | ✅ Alembic V001 → V007（V006：LangGraph checkpoint；V007：durable resume outbox） |
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

*当前报告最近更新：2026-09-21（同步会话工作台与治理总览修复后的 v1.3.0 基线）*
*当前架构版本：1.3.0*
*当前测试基线：以本文件“当前代码基线复核”及 `AGENTS.md` 为准。*
