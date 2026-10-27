# Upgrade State

## Status Summary

Phase 0–4 与 formal-project-uplift Wave A–E 的代码侧工作已完成；当前应用版本为 `1.3.0`，ProjectContext schema 为 `0.9.0`，Alembic head 为 `V008`。默认执行路径仍为 `single_step`；`langgraph_interrupt` 是受控 opt-in，生产启用要求加密 PostgreSQL checkpoint、独立 Fernet key、单 worker 与 fail-closed readiness。

2026-09-21 的真实 PostgreSQL 验收已覆盖暂停、进程重建、恢复、清理、durable resume/outbox 与回滚；验收时 adapter 为 healthy/persistent/encrypted。当前 8000/8501 均未监听，因此运行状态只作为带日期的验收证据，不作为持续在线声明。

## Authority

当前事实按以下顺序判断：

1. `AGENTS.md`、当前业务代码、配置、迁移注册表和测试。
2. `core/version.py`、`pyproject.toml`、Alembic 迁移和 ProjectContext 迁移注册表。
3. `docs/spec/`、`docs/startup.md` 与 `docs/local_setup.md`。
4. `.upgrade/STATE.md`、`.upgrade/MANIFEST.md` 与 `.upgrade/decisions/`。
5. `docs/archive/` 与 `.upgrade/archive/` 中的历史证据。

`.upgrade/AUTHORITY.md` 是经批准权威来源的导航视图，不改变仓库文件本身的所有权。

## Recent Completed Work

- LangGraph interrupt 五阶段实现与验收：V006 checkpoint、V007 durable resume outbox、独立加密、tenant-scoped thread、原子 claim/resume、startup reconcile、严格恢复校验和会话 purge 保护。
- 文档与安全数据面同步：checkpoint 完整上下文副本、密钥生命周期、备份恢复、事故响应和 PII 掩码边界已写入当前规格与合规材料。
- 生产配置加固：生产关闭 demo auto-auth、Docker secrets 纳入两把加密 key、容器 readiness、配置 fail-fast、依赖兼容约束和 `uv run` 启动入口。
- 文档压缩与生命周期整理：`docs/demo-scenarios.md` 去除重复启动说明；旧日志、截图、trace、缓存与 smoke 证据通过受控 cleanup 归档。截图证据现统一位于 `.upgrade/archive/`，具体碰撞安全名称以 `.upgrade/MANIFEST.md` 为准。
- 当前带日期测试基线仍为 `731 passed, 1 skipped`（2026-09-21）；本轮变更另有定向测试和文档检查，最终验证结果记录在本文件的结构化状态与验收摘要中。
- 数据库查询与读写优化（2026-10-27）：新增 Alembic V008（`sessions.version`、JSONB 生成列、租户索引、`human_actions.tenant_id` 回填、`interrupt_records.stage_id` 改 INTEGER、NOT VALID CHECK/FK）；PostgreSQL 写入启用乐观锁与租户一致性校验，`load/delete/list_sessions` 在空 tenant 时拒绝（`system=True` 为启动补偿内部通道）；治理总览/趋势/积压改读生成列并将聚合下推 SQL；`_sync_*` 全面改 `executemany`；连接改为惰性 `psycopg_pool.ConnectionPool`（`DB_POOL_MIN/MAX_SIZE`、`DB_STATEMENT_TIMEOUT_MS`）；新增 `premortem_db_operation_seconds` Histogram。SQLite 保持租户可选兼容。提交 `d25578c`、`8ae102f`。本轮 `750 passed, 1 skipped`，4 个失败均来自工作树中未提交的 `frontend/app.py` 相关 WIP 测试（缺 `api_delete` / `_role_from_token`），非本次改动引入。
- 真实 PostgreSQL 验证（2026-10-27）：本机 PostgreSQL 18（127.0.0.1:5432）以临时库 `ai_workflow_v008_verify` / `ai_workflow_v008_upgrade` 完成实测——V007→V008 迁移、生成列回填、`human_actions.tenant_id` 回填、`interrupt_records.stage_id` 数字转换（非数字按设计置 NULL）、4 个 NOT VALID CHECK 与 `fk_sessions_tenant`、`V008`→`V007`→`V008` 双向迁移；`PostgresSessionStore` 真实读写验证首次插入 version=0、保存 version+1、陈旧写入 409 抛错、跨租户覆盖拒绝、空 tenant 拒绝与 `system=True` 通道、列表分页与生成列投影、治理口径排除 `public_demo`，并确认 `idx_sessions_tenant_updated` 可命中。临时库已删除。注意本机 `.env` 仍指向 `5433`（Docker 映射端口），本机 PostgreSQL 实际监听 `5432` 且 `ai_workflow` 库当前为空表结构。

## Current Blockers

- main 分支保护、Private vulnerability reporting、CodeQL required check、Scorecard 与 GitHub Release 必须远端实查。
- 旧 Docker 镃像是否曾包含敏感文件，需在 Docker daemon 可用后重建并核验；若镜像曾外发，应轮换相关密钥。
- NIST AI 600-1 四项存疑编号、TC260 二手摘要以及未成年人 AI 应用指南定稿内容仍需原文复核。
- ISO 42001 当前仍有系统退役、跨租户集团视图和第三方供应链风险集成三项缺口。
- 四份已停止服务的 stdout/stderr 日志仍被 Windows 句柄占用，暂留 `.upgrade/logs/`；释放句柄后可再次走 cleanup review/apply。

## Validation Commands

- `git status --short`
- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest tests/`
- `make e2e-mock`
- `make doc-check`
- `make version-check`
- `git diff --check`

## Historical Context

完整历史计划、验收报告、决策和原始证据保留在 `docs/archive/`、`.upgrade/archive/` 与 `.upgrade/decisions/`。历史版本号、旧路径、旧测试数量和未勾选项不得作为当前事实。

## current_phase

Phase 4: In progress

## current_task

Obtain remote governance evidence and prepare release configuration

## last_completed_task

Resolved local type, formatting, and documentation validation failures; local checks passed on 2026-09-22

## next_action

Authenticate GitHub maintainer account, verify branch protection and vulnerability reporting, validate SSH remote, then create the approved GitHub Release

## last_update

- Date: 2026-09-22T00:48:40+00:00
- Updated by: project-upgrade-maintainer
- Summary: Entered or refreshed Phase 4.

## last_validation

- Status: passed
- Check: `version-check`
- Environment: local
- Scope: phase-4-final
- Subject: git-worktree `b8a9699450152ed4f8125ed459fc173f5427759d`
- Subject digest: `89027aa75bc1d16e9bf7f8286fb4b1e1253fa3aa590fef840333443f9f5f9469`
- Recorded: 2026-09-22T00:48:00+00:00

## unverified_items

GitHub branch protection, vulnerability reporting setting, and SSH remote authentication remain unverified

## current_blockers

GitHub Release list is empty; branch protection and vulnerability reporting require authenticated maintainer access
