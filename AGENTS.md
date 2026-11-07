# AGENTS.md

本文件适用于整个仓库，是当前事实基线、常用命令、架构不变量与安全边界的**唯一权威源**。所有编码代理在修改代码、文档、配置或升级记录前，应先遵守本文件。

`CLAUDE.md` 是面向 Claude Code 的补充说明，不得与本文件冲突，也**不重复**本文件已有的可漂移事实——它只承载三块本文件未覆盖的内容：目录结构表、Ruff/pytest 细则、`docs/spec/` 状态清单。新增可漂移事实（版本号、测试基线、CI 状态、能力边界）一律只写入本文件。

## 项目现状

- 项目：AI Workflow Premortem，AI 工作流预验尸与人机监督平台；源于本科毕业设计，当前按长期维护的开源项目演进。
- 当前应用版本：`1.8.0`；版本元数据必须同时保持 `core/version.py` 与 `pyproject.toml` 一致。
- 当前数据库迁移头：Alembic `V013`（发布门禁：`service_tokens` 与 `release_gate_checks`；V012 为 P1 加固：`workspace_invitations`、`eval_cases.standard_version`、`eval_runs.case_version_digest` / `target_deployment_version`；V011 为业务闭环真实目标执行元数据；V010 为 `sessions.context_digest`；V009 为 `sessions.projection_state` 与 `eval_runs.pass_criteria` / `llm_judge_suggestion`）；当前 `ProjectContext` schema 保持 `0.10.0`（新增 `target_deployment` / `input_versions` 等可选默认字段，无需 context 迁移）。`alembic/` 迁移目录不得包含 `__init__.py`，否则会遮蔽已安装的 Alembic 包，导致 `from alembic.config import Config` 失败。
- 真实业务库 `ai_workflow` 已升级至 V008（20 会话 / 90 人工动作 / 144 审计事件保留）；V009–V013 为新增列/表迁移，部署环境需执行 `alembic upgrade head`。历史行 `tenant_id` 仍为 NULL，回填前不会进入租户作用域查询与治理统计。旧库升级顺序与备份路径见 `storage/README.md` 与 `.upgrade/backup/`。
- Phase 0–4 代码侧已完成；`docs/archive/plan/phase-*.md` 与 `phase-*-design.md` 是历史实施/设计基线（已归档），不得把其中旧版本、旧行号或未勾选项当作当前事实。
- formal-project-uplift Wave A–E 已完成；剩余工作主要是仓库公开后的远端治理动作，如 CodeQL 转正、main 分支保护和发布设置。权威状态见 `.upgrade/STATE.md`。
- 最近一次本地全量测试基线：`1219 passed, 6 skipped`（2026-11-07 第三阶段发布门禁接入复核；项目 `.venv` pytest，`STORAGE_BACKEND=sqlite` + `CHECKPOINT_BACKEND=memory` + `LLM_MODE=mock` + `WORKFLOW_EXECUTION_MODE=single_step`，70.7s）。6 个 skip 为 3 个 PG/Redis E2E、1 个 PG-only 存储模块与 2 个默认跳过的 live provider 冒烟测试（仅 `LIVE_LLM_TESTS=1` 时执行）；离线 skip 不等于通过，PostgreSQL 侧已用临时 trust 集群实际执行迁移与存储验证。本轮新增测试覆盖发布门禁 allow/block 决策、服务凭证创建/列表/撤销与哈希存储、人类 JWT 拒绝、跨租户 404、过期/撤销 401、72 小时缓存绕过、审计写入失败 fail-closed、OpenAPI 契约、V013 迁移结构与 metrics。此前基线依次为 `1195 passed, 6 skipped`（2026-11-07 第二阶段可靠性加固复核）、`1153 passed, 4 skipped`（2026-11-07 第一阶段业务闭环加固复核）、`1131 passed, 4 skipped`（2026-11-01 P1 业务闭环加固复核）、`1102 passed, 3 skipped`（2026-11-01 业务闭环升级复核）、`1042 passed, 3 skipped`（2026-11-01 安全基线加固复核）、`1016 passed, 3 skipped`（2026-10-31 Milestone 2 Domain Simplification 复核）、`959 passed, 3 skipped`（2026-10-31 Production Safety Baseline）、`894 passed, 1 skipped`（2026-10-31 CI 修复轮复核）、`882 passed, 1 skipped`（2026-10-31，前后端边界加固）、`844 passed, 1 skipped`（2026-10-31，B2 save() 差分同步）、`826 passed, 1 skipped`（2026-10-31，B1 投影直读）、`800 passed, 1 skipped`（2026-10-31）、`798 passed, 1 skipped`（2026-10-29）、`786 passed, 1 skipped`（2026-10-29）、`731 passed, 1 skipped`（2026-09-21）。测试数量会随测试集合变化，不应硬编码为永久断言。
- 本地跑全量测试前需确认 `.env` 的存储后端：若仍是 Docker PostgreSQL 且该库未启动，`uv run pytest tests/` 会因连接等待长时间假死。离线基线须按 `.env.demo` 注入 `STORAGE_BACKEND=sqlite`、`CHECKPOINT_BACKEND=memory`、`LLM_MODE=mock`。
- 前端按 MVC 分层：`frontend/models/`（配置、认证、API 客户端、状态投影）、`frontend/controllers/`（按业务域编排动作）、`frontend/views/`（侧栏、工作台与各面板）；`frontend/app.py` 仅做入口装配，`frontend/components/` 为可复用视图组件。依赖方向固定为 models ← controllers ← views ← app。
- 治理总览当前只聚合真实业务会话（`business_internal` / `sensitive_personal`）；四个内置场景及其他 `public_demo` 会话必须与总览、趋势、积压动作和对应业务 Gauge 隔离。前端必须明确展示该统计口径，正常零数据不得表述为加载失败。
- 业务闭环不变量：证据生命周期为派生状态（submitted/verified/adopted），未核验证据不得解除高风险门禁；high/critical 风险项必须有已复核且绑定当前评估版本的 `RiskTreatment`；评估版本变化后原样重提处置也必须清空旧复核；`SessionState.COMPLETE` 仅表示评估完成，上线批准是独立 `ProjectApproval`，报告生成/导出不产生审批；`EvalRun.execution_kind` 必须区分模拟与 `real_target_execution`，只有当前评估版本、当前用例版本、当前目标部署下 `execution_outcome=success`、`judge_result=passed`、`judge_mode=human` 且存在带非空 `human_comment`/`reviewer_id` 的 `human_label=passed` 人工校准的运行，并且覆盖同一 completed `target_http` 评估批次中的全部必测用例，才计入上线批准；人工校准会以 approve/reject 关闭对应 `eval_run` 阻断动作。批准后驳回处置、改判关键测试、修改实际输出或人工判定依据、新增高危安全发现必须使 `effective_status` 变为 `invalidated`，历史批准只追加不删除。public_demo 会话豁免风险处置门禁与上线批准。
- 团队与身份不变量：每次注册创建独立工作区且创建者为 admin；同租户成员只能通过 `workspace_invitations` 加入；复核身份只取 JWT `user_id`，请求体不得接受 `reviewer_id`；`/auth/refresh` 必须重新读取当前用户角色，不得沿用旧刷新令牌中的 role。
- 发布门禁不变量：`GET /release-gate/{session_id}` 只接受租户级 service token（scope 固定 `release_gate:read`，原始值只返回一次、库内只存 SHA-256、默认 90 天、可撤销），人类 access/refresh JWT 不得通过。只有当前 `ProjectApproval.effective_status=approved` 且 `release_readiness.can_approve=true` 才返回 HTTP 200 + `decision=allow`；未批准、被驳回、stale、invalidated、public_demo、跨租户、凭证无效/过期/撤销、门禁计算或审计写入失败一律阻断。门禁必须绕过 72 小时 `context_cache` 直接读取存储；每次通过认证的检查写入 append-only `release_gate_checks`，写入失败不得返回 allow；响应不得包含会话正文、用户材料或审批备注。
- 字段加密不变量：`goal` 必须与 `research_target` 一同加密；历史明文通过 `scripts/encrypt_legacy_goal.py` 回填，旧代码回滚前必须解密或恢复备份。
- 模型失败契约：真实 provider 超时/限流/鉴权/连接/5xx 统一由 `core/llm/errors.py` 分类，API 返回 HTTP 502 固定 `error_code` / `retryable`；日志与 trace 只记录错误码与异常类型，不记录 provider 原文、提示词或密钥。`LLM_TIMEOUT_SECONDS`（默认 120）/ `LLM_MAX_RETRIES`（默认 1）控制超时与 SDK 重试。
- 目标响应边界：`target_http` 流式读取并受字节硬上限约束（由 `TARGET_SYSTEM_MAX_RESPONSE_CHARS × 4 + 4096` 推导，最低 16 KB）；超限返回 `response_too_large` 且不解析残缺 JSON，错误文本最多 500 字符；目标执行不自动重试。
- 留存清理顺序：先提交数据库删除（审计归档 + 会话行），再清理 checkpoint 与缓存；checkpoint 清理失败只记录错误与指标，不回滚已删除会话，下一轮继续清理剩余候选。
- 录制测试基线必须走 `uv run`（项目 `.venv`）。用系统 Python 直接跑 `python -m pytest` 会因缺少 `prometheus-fastapi-instrumentator` 等主依赖触发 7 处 `importorskip` 跳过，得到 `623 passed, 8 skipped` 的降级结果——该数字不是有效基线。

## 事实来源优先级

发生冲突时，按以下顺序判断：

1. 当前可执行的业务代码、配置、迁移注册表和测试。
2. `core/version.py` / `pyproject.toml`、Alembic 迁移文件、`core/migrations/registry.py`。
3. 当前规格文档 `docs/spec/`、运行指南 `docs/startup.md` / `docs/local_setup.md`。
4. `.upgrade/STATE.md` 与 `.upgrade/decisions/` 中的最新决策。
5. `docs/archive/plan/` 历史计划（已归档）、CHANGELOG 历史条目和旧验收快照。

禁止为了让代码“符合旧文档”而回退真实业务行为；应先验证代码，再更新失效文档。

## 工作方式

- 开始任务先运行 `git status --short`，识别并保留用户已有改动；当前工作树可能不是 clean。
- 搜索优先使用 `rg` / `rg --files`。
- 只修改任务范围内文件，不回退、覆盖或格式化无关改动。
- 未经明确要求，不执行提交、推送、打 tag、创建 release 或修改远端仓库设置。
- 不使用 `git add .`；如用户明确要求 staging，只能 `git add <specific-file>`。
- 删除文件前先核实引用、跟踪状态和替代内容；不得删除 `.upgrade/` 外文件，除非用户明确授权。
- 业务改动必须配套测试；纯文档改动至少运行 `make doc-check` 和 `make version-check`。
- 完成前运行 `git diff --check` 与 `git status --short`。

## 常用验证命令

```bash
uv sync --all-extras
make lint
make typecheck
make test
make e2e-mock
make doc-check
make version-check
```

- `make doc-check` 当前是 CI 阻断项，扫描 37 份当前项目 Markdown（排除 `.upgrade/`、archive、运行时产物和缓存）。
- CI 中 mypy 仍处观察期（non-blocking）；`production-safety` 与 `docker-full-integration` 已是 blocking job，不得再写回 continue-on-error。`production-safety` 覆盖 V008→动态 head（当前 V013）迁移升级/回滚、production safety 测试集、PostgreSQL + Redis 业务 E2E，并设置 `PRODUCTION_SAFETY_REQUIRED=1` 使缺少服务时失败而非跳过。CI 的 head 断言必须由 `ScriptDirectory.get_current_head()` 计算，不得硬编码版本。
- CI 单元测试步骤会把 `.env.demo` 复制为 `.env`；`core/config.py` 的 `extra="ignore"` 是共享 env 文件的必要条件（`.env.demo` / `.env.example` 含前端专用 `DEMO_*` 与容器键 `SQLITE_PATH`），移除该项会让 CI 与 `make demo-*` 在导入阶段即失败。CI 的 lint job 只阻断 Ruff（`make lint`）；`make audit` 作为独立 `continue-on-error` 观察步骤运行，本地 `make security-check`（lint + audit）仍保持严格。2026-11-01 实测外部 advisory 库共 124 条 unique advisory / 19 个包：pillow 受 streamlit `pillow<13` 上限、ecdsa 无修复、langgraph-checkpoint-postgres 被 V006 固定 `3.0.5`，其余可升级项列入 `.upgrade/STATE.md` 阻塞项分诊。
- 离线开发优先使用 `make demo-api` + `make demo-ui`（Mock LLM + SQLite）。
- Docker Lite 使用 `make lite-up`；完整栈使用 `make setup` + `make prod-up`。

## 架构不变量

- 状态转换由确定性代码控制，LLM 只生成分析内容，不决定流程跳转。
- 项目风险等级由 `core/risk` 的六因子确定性模型产生（`impact` / `autonomy` / `data_sensitivity` / `reversibility` / `scale` / `external_exposure`）；关键词库只用于旧上下文推断适配器，LLM 只能提供解释文本。人工 override 必须记录原等级/请求等级/生效等级/floor/原因/操作者/角色/租户并写审计事件，下调不得低于确定性 floor。
- Stage 3 采样必须走 `core/coverage/policy.py`：HIGH/CRITICAL 必须覆盖全部高风险节点，LOW/MEDIUM 的预算型抽样必须满足 `STAGE3_MIN_COVERAGE_RATIO` 与配置的采样数下限；Gate 对每个高风险节点的 EvalCase 最低数量由 `STAGE3_MIN_CASES_PER_HIGH_RISK_NODE` 控制。
- `core/session_service.py` 是兼容 facade；五个域服务位于 `core/services/`，不得在模块级互相导入或导入 facade。`core/risk`、`core/coverage`、`core/governance/action_state.py` 不得反向依赖 `core/gates` 或服务层。
- 未知/非法 workflow state 必须 fail-closed：`core/workflow_state_service.py` 将存储边界或运行路径上的未知状态改写为 `RECOVERY_REQUIRED`，runner 不执行任何节点、不回退 `INIT`；`ERROR` / `RECOVERY_REQUIRED` 只能通过 `POST /sessions/{session_id}/workflow/recover` 显式恢复并写审计事件。
- HIGH/CRITICAL 场景不允许弱 fallback：Markdown 结构化解析失败、监督策略无法显式生成、Gate 规则异常或 Gate 落表失败均必须阻断推进（`GateDataError` / critical blocker），public_demo 场景除外。
- 默认执行路径是 `single_step`；`langgraph_interrupt` 是受控 opt-in 路径，启用时必须使用加密 PostgreSQL checkpoint、单 worker 和 fail-closed readiness。
- 高风险推进必须经过风险自适应门禁和必要的 `PendingHumanAction`。
- API 路由只做协议适配，核心逻辑应位于 `core/`、`graph/`、`stages/` 或 `storage/`。
- PostgreSQL schema 迁移只通过 Alembic；`core/migrations/` 仅用于历史 `ProjectContext` JSON 升级，二者不得混用。
- 早于 Alembic 手工创建的旧库不能直接 `alembic upgrade head`：V001 的租户索引依赖 `sessions.tenant_id`，而 `CREATE TABLE IF NOT EXISTS` 不会为已存在表补列。必须先备份、按 V001 基线补齐缺失列、写入 `alembic_version` 后再升级。
- 门禁规则新增/删除时必须同步 `core/gates/rules/manifest.py`、相关测试与规格文档。
- 新增场景时同步 `scenarios/manifests/`、example input、domain profile/mock fixture（如需要）及场景测试。

## 当前安全与合规边界

- `make setup` 会生成独立的字段加密与 checkpoint Fernet key，并通过 Docker secrets 注入；非 Docker 部署仍需显式配置。生产必须检查 `/health.data_encryption == enabled`，中断模式还必须确认 adapter 为 persistent/encrypted/healthy。`APP_ENV=production` 启动时 `Settings` 会拒绝 `LLM_MODE=mock`、`STORAGE_BACKEND=sqlite`、`DEMO_AUTO_AUTH=true` 以及缺失或非法 `DATA_ENCRYPTION_KEY`。
- 留存执行器已落地：`core/retention_service.py` 在应用启动后按 `RETENTION_SWEEP_INTERVAL_SECONDS` 周期执行，`RETENTION_ENABLED` 默认开启但 `RETENTION_DRY_RUN` 默认 `true`（只统计不删除）；只有显式设置 `RETENTION_DRY_RUN=false` 才会删除到期会话与审计行。`SESSION_RETENTION_DAYS=0` 表示永久保留，默认不清理会话；`AUDIT_RETENTION_DAYS` 到期清理同时覆盖活动审计与归档审计表。它是进程内调度，不依赖外部 cron，多 worker 部署时各 worker 各自扫描（事务与行数校验保证不会重复删除同一行）。
- `PII_MASK_BEFORE_LLM` 默认关闭，仅影响未被升级的 `business_internal` / `public_demo` 出站消息；聊天正文在 `send_message` 进入模型前、补充材料在加入时统一扫描四类 PII，命中即升级 `sensitive_personal`，其后所有外部 LLM 消息强制掩码（`core/llm/outbound_guard.py`），不受该开关影响。
- 事件与审计写入统一经 `core/data_protection.py` 脱敏：`business_internal` / `sensitive_personal` 的自由文本字段写成 `{"_redacted": true, "sha256": ..., "length": ...}`，用户原文不得进入 `session_events` / `audit_events` payload；`public_demo` 保持可读。字段级加密覆盖 `research_target` / `goal` / `user_materials` / 用户材料型 evidence / conversation / pending actions / report content，PostgreSQL 或 `APP_ENV=production` 下缺失密钥必须 fail-closed（`FieldDecryptionError`）。
- main 分支保护是否已在 GitHub 后台开启，必须以远端实查为准；本地当前状态记录为待维护者执行。

## 文档与升级记录

- `docs/spec/` 描述当前实现；历史基线必须显式标注，不得与当前事实混写。
- `docs/archive/plan/` 是历史计划/设计记录（已归档），保留用于追溯；除非明确要求，不批量删除或重写历史内容。
- 修改文档索引结构时同步 `docs/README.md`。
- 所有升级维护操作必须遵守下方受控块，并在任务完成后更新 `.upgrade/STATE.md`。

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

<!-- project-upgrade-maintainer:start -->
## Project Upgrade Governance

This repository contains a governed upgrade workspace at `.upgrade/`. Before reading, planning, or modifying upgrade-workflow artifacts, read `.upgrade/AGENTS.md`, which is the canonical scoped governance contract for `.upgrade/**`.

Canonical context: `.upgrade/CONFIG.json` (active modules), `.upgrade/AUTHORITY.md` / `.upgrade/AUTHORITY.json` (approved project authority map), `.upgrade/ARTIFACTS.json` (registered artifact policies), `.upgrade/STATE.md` (current state), `.upgrade/MANIFEST.md` (inventory), `.upgrade/docs/UPGRADE_REQUIREMENTS.md` (requirements), and `.upgrade/docs/UPGRADE_PLAN.md` (upgrade plan). When configured, `.upgrade/delivery/POLICY.json` defines approved minimum delivery evidence. Additional phase/evidence/lifecycle resources materialize only when their modules are active.

Do not bypass the review -> exact approval -> apply lifecycle for governed mutations. Protected or sensitive collection requires exact-path authorization again at apply time. Repository/local instructions remain authoritative for their own scope; surface conflicts instead of silently resolving them.
<!-- project-upgrade-maintainer:end -->
