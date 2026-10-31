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
- 当前带日期测试基线为 `750 passed, 1 skipped`（2026-10-29 复核，与 2026-10-27 首次记录一致；项目 `.venv`，`sqlite` + `memory` checkpoint）；4 条失败来自工作树中未提交的前端 WIP 测试，不计入基线。上一轮 2026-09-21 基线为 `731 passed, 1 skipped`。
- 数据库查询与读写优化（2026-10-27）：新增 Alembic V008（`sessions.version`、JSONB 生成列、租户索引、`human_actions.tenant_id` 回填、`interrupt_records.stage_id` 改 INTEGER、NOT VALID CHECK/FK）；PostgreSQL 写入启用乐观锁与租户一致性校验，`load/delete/list_sessions` 在空 tenant 时拒绝（`system=True` 为启动补偿内部通道）；治理总览/趋势/积压改读生成列并将聚合下推 SQL；`_sync_*` 全面改 `executemany`；连接改为惰性 `psycopg_pool.ConnectionPool`（`DB_POOL_MIN/MAX_SIZE`、`DB_STATEMENT_TIMEOUT_MS`）；新增 `premortem_db_operation_seconds` Histogram。SQLite 保持租户可选兼容。提交 `d25578c`、`8ae102f`。本轮 `750 passed, 1 skipped`，4 个失败均来自工作树中未提交的 `frontend/app.py` 相关 WIP 测试（缺 `api_delete` / `_role_from_token`），非本次改动引入。
- Docker 构建上下文清理（2026-10-28）：`.dockerignore` 新增 `/*.txt`、`.uv-cache/`、`.uv/`、`.screenshots/`、`/Makefile`，阻止内部方案与本地缓存进入镜像；`pyproject.toml` / `uv.lock` 保留，因为 deps 构建阶段仍依赖。镜像拉取慢已定位为 Docker Desktop VM 内 DNS 首次解析返回空、docker.io 解析被污染且无 HTTPS 代理、ghcr.io 无镜像源，叠加首次构建基础镜像未缓存。
- 真实 PostgreSQL 验证（2026-10-27）：本机 PostgreSQL 18（127.0.0.1:5432）以临时库 `ai_workflow_v008_verify` / `ai_workflow_v008_upgrade` 完成实测——V007→V008 迁移、生成列回填、`human_actions.tenant_id` 回填、`interrupt_records.stage_id` 数字转换（非数字按设计置 NULL）、4 个 NOT VALID CHECK 与 `fk_sessions_tenant`、`V008`→`V007`→`V008` 双向迁移；`PostgresSessionStore` 真实读写验证首次插入 version=0、保存 version+1、陈旧写入 409 抛错、跨租户覆盖拒绝、空 tenant 拒绝与 `system=True` 通道、列表分页与生成列投影、治理口径排除 `public_demo`，并确认 `idx_sessions_tenant_updated` 可命中。临时库已删除。本机 `.env` 已改为 `POSTGRES_PORT=5432` 以匹配容器内端口（宿主进程连 Docker DB 时需临时改为 `5433`）；`secrets/` 已补齐 `data_encryption_key` 与 `checkpoint_encryption_key`，`docker compose config` 校验通过。真实业务库 `ai_workflow` 已于 2026-10-27 升级到 V008：先 `pg_dump` 备份到 `.upgrade/backup/ai_workflow_legacy_20261027.sql`，再补齐 V001 基线缺失列（`sessions.tenant_id` 等 30 列），最后 `alembic upgrade head`（V001→V008）。旧数据无损（20 会话 / 90 人工动作 / 144 审计事件）；历史行 `tenant_id` 均为 NULL，默认租户作用域查询不可见，待按实际归属回填。
- 数据库迭代收尾与工作区整理（2026-10-29）：复核 V008 迁移头、真实业务库数据量与数据库相关文档，补齐 `AGENTS.md` 业务库状态与基线日期；`ruff format` 修正 3 个存量文件后复跑 `750 passed, 1 skipped`（4 条失败仍为前端 WIP）。`.upgrade` 执行 `sync` 修复忽略链路，cleanup 归档 42 项旧 trace/日志、31 个临时脚本移入回收站，并为 `.upgrade/backup/` 的 SQL 转储与 daemon 备份注册 runtime/ignore 策略。
- 租户一致性补丁（2026-10-29）：`api/main.py` 的 429 审计在 `session_store.save` 后同步 `context_cache.set`；`StaleContextError` 处理器按 Bearer 令牌解析租户并失效缓存，消除"409 → reload → 再次命中旧版本"循环；内部跨租户通道由布尔 `system=True` 收窄为 `storage.access.SYSTEM_ACCESS` 哨兵（Enum 单例，非哨兵值抛 `TenantIsolationError`，每次合法使用写 warning 日志），`load/delete/list_sessions` 双后端同步；新增 `PostgresSessionStore.backfill_orphan_sessions()` 与 `scripts/backfill_session_tenants.py`（默认 dry-run、仅回填 `tenant_id IS NULL`、单事务联表回填 `human_actions` / `interrupt_resume_outbox`），为历史 20 个无归属会话提供幂等回填通道。新增 `tests/test_api_cache_invalidation.py`、`tests/test_storage_tenant_backfill.py`，扩展 `tests/test_storage_tenant_and_locking.py`。
- 留存执行器与门禁评估生命周期（2026-10-29）：新增 `core/retention_service.py`，lifespan 启动后按 `RETENTION_SWEEP_INTERVAL_SECONDS` 周期执行；`RETENTION_ENABLED` 默认 `true`、`RETENTION_DRY_RUN` 默认 `true`（只统计不删除），`/health` 新增三个留存字段。到期会话复用 `purge_session` 生命周期（checkpoint → 审计归档 → 投影表 → 缓存失效）；`audit_events` 与 `audit_events_archive` 按 `RETENTION_BATCH_SIZE` 分批清理；`SESSION_RETENTION_DAYS=0` 仍表示永久保留。`purge_session` 双后端同步删除 `gate_evaluation_records`；`backfill_orphan_sessions` 与 CLI 增加该表回填；评估主键改为完整 UUID。新增 `tests/test_retention_service.py`，全量 `786 passed, 1 skipped`；Ruff、mypy、doc-check、version-check 通过。
- 中断恢复 outbox 周期重试与 chat 异常映射（2026-10-29）：`core/execution_service.py` 新增进程内调度器，仅在 `langgraph_interrupt` 模式下于启动对账后按 `INTERRUPT_RESUME_RETRY_INTERVAL_SECONDS`（默认 600 秒，0=只做启动对账）重试 pending/failed 行，批量上限 `INTERRUPT_RESUME_RETRY_BATCH_SIZE`（默认 100）；`/health` 新增 `interrupt_resume_scheduler`，shutdown 先停调度器再关 checkpoint runtime 与连接池。`api/routers/chat.py` 移除 `except Exception → 500` 兜底，恢复全局 409/404 映射且不再泄露内部异常文本。新增 `tests/test_interrupt_resume_scheduler.py` 与两条 chat 异常映射测试。
- 前端 WIP 回退（2026-10-29）：工作树 `frontend/app.py` 为未完成重构（删 714 行内联实现，改为 import 不存在的 `api_client` / `live_oversight`），导致 Streamlit 启动即 `ModuleNotFoundError` 且 4 条前端契约测试失败。经确认后将 `frontend/app.py` 与 3 个前端契约测试文件恢复为 HEAD 内联版本，WIP 备份至 `.upgrade/backup/frontend_wip_20261029/`。恢复后全量 `773 passed, 1 skipped`（SQLite + memory，32.1s）。
- 前后端契约补全（2026-10-29）：`api/routers/` 的 session、oversight、stage 三组路由补齐 `response_model`（会话详情/动作/审计/阶段就绪与门禁/阶段解析/推进决策/门禁报告/删除/导出/rerun 等），嵌套响应引用 `ProjectContext`、`PendingHumanAction`、`AuditEvent`、`ActionResolutionLog`、`StageReadiness`、`StageGateResult`、`StageAdvancementDecision`、`GateReport` 等既有领域模型；`api/schemas.py` 新增 `RenameSessionResponse`、`UpdateDataClassificationResponse`、`DeleteSessionResponse`、`StageOperationResultResponse` 及材料/flag/导出/阶段解析四个响应模型。`update_data_classification` 的分级顺序、降级门槛、审计与持久化下沉到 `SessionService.update_data_classification`，路由只保留角色准入与 `DataClassificationDowngradeError → 403` / `ValueError → 404` 映射。新增 `tests/test_api_response_contract.py`（OpenAPI ref 断言 + 服务层降级规则），并同步移除两个测试 fixture 对已删除的路由级 `session_store` / `context_cache` patch。全量 `798 passed, 1 skipped`；Ruff、mypy 通过。注：`uv run ruff check .` 因未跟踪的 `.upgrade/backup/frontend_wip_20261029/` 备份副本触发 S101，属既有备份产物，不在改动范围。
- 前端 MVC 拆分（2026-10-31）：`frontend/app.py`（2515 行）拆为 `models/`（config、auth、api_client、stage_envelope、session_state、mappings）、`controllers/`（auth/session/stage/governance/eval/report 六个按业务域控制器）、`views/`（sidebar、workbench、welcome、live_oversight、panels/*）；`app.py` 仅保留 `set_page_config`、认证守卫、状态初始化与侧栏/工作区装配。严格行为等价：`session_state` 键、widget key、渲染顺序、文案、rerun/stop 语义、API 路径与超时不变；70 个原样迁移函数经 AST 对比与备份 `app.py` 完全一致（无缺失、无差异）。4 个前端契约测试改为扫描 `frontend/**/*.py`，新增 `tests/test_frontend_mvc_imports.py`（模块可导入 + 入口调用顺序）。后端 `api/`、`core/`、`storage/`、`graph/` 未改动。全量 `800 passed, 1 skipped`（SQLite + memory + mock，30.7s）；Ruff、mypy（161 files）、doc-check、version-check 通过。备份位于 `.upgrade/backup/frontend_mvc_20261031/`。
- 测试环境提示（2026-10-31）：直接 `uv run pytest tests/` 时若 `.env` 仍指向 Docker PostgreSQL 而该库未运行，会因连接等待表现为数分钟以上的假死（曾观察到两组并发 pytest 卡在 35%–62%）。复现基线需按 `.env.demo` 注入 `STORAGE_BACKEND=sqlite`、`CHECKPOINT_BACKEND=memory`、`LLM_MODE=mock` 等变量；测试本身不修改 `.env`。
- 前端数据传输链路优化（2026-10-31）：三阶段提交 `73537f2`（`api_client` 改用模块级共享 `requests.Session` + `HTTPAdapter(pool_maxsize=20)`，复用 keep-alive 连接）、`fd8e303`（`st.session_state` 会话级 TTL 读取缓存覆盖 health/场景/会话列表与面板只读接口，写入路径按前缀失效，侧栏「刷新」改为真实清缓存并重拉）、`7a95cbc`（`render_action_queue` 去掉每次 rerun 的无条件 `refresh_actions()`、`gate_panel` 复用 `stage_advancement_decisions` 仅在缺失时回源、`diagnostics_panel` 去掉空列表触发的二次请求、`refresh_actions`/`select_session` 丢弃过期推进判定）。新增 `tests/test_frontend_transport_cache.py`（6 条缓存与连接池契约）。仅前端传输层，不动后端契约与存储层。全量 `806 passed, 1 skipped`（SQLite + memory + mock，12.7s）；Ruff、doc-check、version-check 通过。

## Current Blockers

- main 分支保护、Private vulnerability reporting、CodeQL required check、Scorecard 与 GitHub Release 必须远端实查。
- 旧 Docker 镜像是否曾包含敏感文件，需在 Docker daemon 可用后重建并核验；若镜像曾外发，应轮换相关密钥。
- NIST AI 600-1 四项存疑编号、TC260 二手摘要以及未成年人 AI 应用指南定稿内容仍需原文复核。
- ISO 42001 当前仍有系统退役、跨租户集团视图和第三方供应链风险集成三项缺口。
- `.upgrade/tmp/.trash/` 仍有 32 个已清理文件等待自然过期；四份旧 stdout/stderr 日志的句柄占用已随 2026-10-29 cleanup 解除，今日 pytest 日志保留在 `.upgrade/logs/`。

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

Closed database iteration review, synced docs, and completed .upgrade cleanup with backup artifact policies on 2026-10-29

## next_action

Authenticate GitHub maintainer account, verify branch protection and vulnerability reporting, validate SSH remote, then create the approved GitHub Release

## last_update

- Date: 2026-10-29T11:27:56+00:00
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
