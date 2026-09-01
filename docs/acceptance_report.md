# AI Workflow Pre-mortem 当前验收报告

> 本文件记录当前 v1.3.0 代码基线与回归摘要。v1.2.1 四阶段 E2E 快照、历史缺陷详录和原始统计已归档至 [`acceptance-history-v1.2.1.md`](archive/verification-reports/acceptance-history-v1.2.1.md)；2026-07-18 四种启动方式的完整历史报告见 [`startup-methods-e2e-20260718.md`](../.upgrade/archive/reports/startup-methods-e2e-20260718.md)。

## 当前代码基线复核（2026-09-01）

本节记录当前工作区的文档—代码一致性复核结果。

> 2026-07-25 一轮曾把 `623 passed, 8 skipped` 记为当前基线，该数字系用系统 Python 而非项目 `.venv` 运行所致（缺 `prometheus-fastapi-instrumentator` 触发 7 处 `importorskip`），已于 2026-07-31 更正。录制基线请统一使用 `uv run pytest` / `make test`。

| 验证项 | 当前结果 |
|------|------|
| 版本一致性 | ✅ `core/version.py` = `pyproject.toml` = 1.3.0 |
| 全量测试 | ✅ `666 passed, 1 skipped`（项目 `.venv` pytest，2026-09-01 复核；较 660 基线新增 6 条前端会话删除契约测试） |
| 文档一致性检查 | ✅ 扫描 50 个当前项目 Markdown 文件，0 处违规（2026-07-31） |
| 数据库迁移链 | ✅ Alembic V001 → V005 |
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

*当前报告最近更新：2026-08-15（压缩历史验收详录并保留归档入口）*
*当前架构版本：1.3.0*
*当前测试基线：以本文件“当前代码基线复核”及 `AGENTS.md` 为准。*
