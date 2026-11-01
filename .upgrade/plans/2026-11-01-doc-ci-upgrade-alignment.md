# 文档、GitHub CI/CD 与 .upgrade 全面对齐 — 实施方案

## 1. 目标与边界

目标：以当前源码、配置、迁移和实测结果为依据，消除过期/矛盾/未经验证的完成声明，使根文档、`docs/`、GitHub Actions 与 `.upgrade/` 在同一事实上对齐。

范围外（明确不做）：扩展业务功能；新增 CI job；修改 `scripts/version_check.py` / `doc_consistency_check.py` 检查规则；重写 `docs/archive/**` 与 `.upgrade/archive/**` 历史内容；伪造未执行或无法执行的检查结果。

## 2. 已核实基线（2026-11-01）

### 2.1 本地事实

| 项 | 事实 | 证据 |
|---|---|---|
| 应用版本 | `1.7.0` | `core/version.py:3-6`、`pyproject.toml:4`、`uv.lock`、`CHANGELOG.md:7` |
| Alembic head | `V012`（V011→V012，`down_revision="V011"`） | `alembic/versions/V012_p1_governance.py:19-20`；`alembic/` 无 `__init__.py` |
| ProjectContext schema | `0.10.0`（legacy `0.6.0-alpha.8`） | `core/migrations/registry.py:10-11` |
| doc-check | 实测通过：37 份 Markdown，0 违规 | 本次计划阶段实际运行 |
| version-check | 实测通过：`Version metadata OK: 1.7.0` | 本次计划阶段实际运行 |
| Git 状态 | 本地 `HEAD=7966f9d`；`origin/main=16624b9`；工作树 49 个已跟踪文件修改 + 11 个未跟踪文件（v1.7.0 P1 改动） | `git status --short`、`git log origin/main..HEAD` |
| 代码侧已修复的 CI 根因 | `7966f9d` 已跟踪 `core/coverage/**` 并把 `.gitignore:33` / `.dockerignore:36` 的 `coverage/` 锚定为 `/coverage/`；未提交的 `ci.yml` 已改为动态 `ScriptDirectory.get_current_head()` | `git show 7966f9d --stat`、`git diff .github/workflows/ci.yml` |

### 2.2 远端 CI 现状（同一提交证据）

远端 `main` 最近三次运行：

| run | SHA | 事件 | 结论 | 关键失败 |
|---|---|---|---|---|
| [41281614067](https://github.com/gome09/ai-workflow-premortem-pure/actions/runs/41281614067) | `16624b9` | push | **failure（4/4 job 失败）** | 见下 |
| 41281532538 | `4fbffc6` | push | cancelled（被 concurrency 取消） | — |
| 41206676638 | `4ad40d0` | push | failure | 历史失败 |

`16624b9` 的失败根因（已逐 job 核实日志）：

1. `lint-and-unit-tests`：`Security check` 步骤 `ruff check .` 报 2 处错误（import block 未排序），`make lint` exit 1 → 其后步骤全部 skipped。
2. `docker-lite-integration` / `docker-full-integration`：API 容器 `ModuleNotFoundError: No module named 'core.coverage'`（该提交的 `.gitignore` 仍为未锚定 `coverage/`，包未入库），健康检查超时。
3. `production-safety`：迁移步骤硬编码 `grep -q "V010 (head)"`，实际 head 为 V011，`Migration upgrade V008 -> head` 失败。

以上三项在本地工作树中均已修复，但**尚未提交/推送**，因此当前远端没有任何一个提交同时包含 v1.7.0 与全部 CI 修复。

### 2.3 远端治理与未验证项

| 项 | 状态 |
|---|---|
| CodeQL workflow | 最近 push 运行成功（run 41281614061，SHA `16624b9`） |
| Scorecard workflow | 最近成功 2026-10-26（SHA `834226e`） |
| main 分支保护 / Private vulnerability reporting / CodeQL required check / GitHub Release | 未验证（需维护者在 GitHub 后台实查） |
| 本地 PostgreSQL + Redis 业务 E2E | 未验证（本机 Redis/Docker 未运行），委托 CI `production-safety` |

## 3. 漂移清单（只列需改项）

### 3.1 根文档与使用指南

| 文件:位置 | 现状 | 改为 |
|---|---|---|
| `README.md:14` | 版本 `v1.3.0` | `v1.7.0` |
| `README.md:51-64` 核心功能表 | 无业务闭环、工作区邀请、真实目标测试 | 追加 3 行：风险处置、上线批准、真实目标测试/团队工作区；并注明边界（不做多工作区切换、不发送邀请邮件） |
| `README.md:130-136` 测试节 | 只写 `uv run pytest tests/ -q`，并称“使用内存存储” | 明确离线基线需 `.env.demo` 的 `sqlite + memory + mock`；提示若 `.env` 指向未启动 PostgreSQL 会长时间等待；4 个 skip 为 PG/Redis E2E 与 PG-only 存储模块，由 CI `production-safety` 覆盖 |
| `docs/README.md:10` | “当前 v1.3.0 代码基线” | “当前 v1.7.0 代码基线与回归摘要” |
| `docs/README.md:21` | supply-chain 描述含糊 | 改为“CI 权限/依赖审计/CodeQL 触发/Scorecard 已实现；main 分支保护与 CodeQL required check 待远端确认” |
| `docs/acceptance_report.md:3,5-22,42-44` | 当前基线仍为 v1.3.0 / `800 passed` / `V001→V008` / doc-check 38 份 / schema 0.9.0 | 更新为 1.7.0、实测测试数字、`V001→V012`、doc-check 37 份、schema 0.10.0；原 2026-10-31 段降级为“历史基线（v1.3.0）”并保留 |
| `docs/startup.md:3` | Last updated 2026-07-31 | 2026-11-01；在生产栈章节补充：启动时 `initialize()` 自动 `alembic upgrade head`，手工迁移用 `docker compose run --rm api python -m alembic upgrade head`（覆盖 V009–V012） |
| `docs/local_setup.md:3,60` | Last updated 2026-07-31；`DATA_ENCRYPTION_KEY` 为空“明文存储并告警” | 更新日期；改为“PostgreSQL 或 `APP_ENV=production` 缺失密钥时解密 fail-closed（`FieldDecryptionError`），SQLite 开发模式才允许明文并告警”；补 `APP_ENV` 关键变量行 |
| `.github/ISSUE_TEMPLATE/bug_report.md:23` | 示例版本 `v1.3.0` | “见 `core/version.py`” |

### 3.2 当前规格（docs/spec）

| 文件:位置 | 现状 | 改为 |
|---|---|---|
| `docs/spec/governance-platform.md:3-4` | Status 只到 v1.3.0；Last updated 2026-07-27 | Status 追加“v1.7.0 业务闭环加固（工作区邀请/评估版本 2.0/发布证据批次/批准失效）”；日期 2026-11-01 |
| `docs/spec/security-model.md:3,25-28,49` | Last updated 2026-09-21；“首个注册用户 admin，后续默认 viewer”；认证接口缺邀请端点 | 更新日期；改为“每次注册创建独立工作区且创建者为 admin；同租户成员仅通过 `workspace_invitations` 加入；`/auth/refresh` 重读角色；EvalRun 复核身份取 JWT”；补 `/auth/invitations` 三条端点 |
| `docs/spec/supply-chain-security.md:4,38,79-85,89-104` | §2 称“三个 job”；§4 CodeQL 只描述手动+cron；§5 称 pip-audit `continue-on-error` 不阻断 | 改为四个 job（含 `production-safety`）；CodeQL 已含 main push/PR，required check 待远端；pip-audit 为 `make security-check` 阻断并登记 `PIP_AUDIT_IGNORES`；日期 2026-11-01 |
| `docs/spec/architecture.md:221` | 存储迁移只列到 V008 | 补 V009–V012 一行，并指向 `storage/README.md` 现状 |
| `docs/spec/api-reference.md:6` | `Status: Implemented（HTTP 路由按当前源码静态提取）` | 已覆盖邀请/处置/批准/目标部署/用例标准端点，核对后仅更新时间标注（如有） |

### 3.3 GitHub Actions 与验证配置

| 文件 | 检查项 | 结论/动作 |
|---|---|---|
| `.github/workflows/ci.yml:16-58` | `uv sync --all-extras --frozen`、Python 3.11、`security-check`、`typecheck`（唯一 `continue-on-error`）、`doc-check`、`version-check`、`cp .env.demo .env` + `test-cov` | 与 AGENTS 声明一致；确认 `security-check` 为阻断、mypy 仍观察期 |
| `.github/workflows/ci.yml:159-192` | head 动态计算、V008→head 升级/回滚、新增 `test_postgres_p1_storage.py`、`PRODUCTION_SAFETY_REQUIRED=1` | 已是修复后版本；核对无 `V0xx (head)` 字面量 |
| `.github/workflows/ci.yml:60-96,197-257` | docker-lite / docker-full 阻断、7 容器断言、业务 E2E | 无 `continue-on-error`；`core.coverage` 入库后应恢复健康检查 |
| `.github/workflows/codeql.yml` / `scorecard.yml` | 权限与触发 | 已 `contents: read`（CodeQL 另加 `security-events: write`）；无失效 action 版本 |
| `tests/test_ci_migration_head.py` | 动态 head 与 `alembic/__init__.py` 缺失 | 保留并纳入提交 1，作为 CI 配置回归测试 |

执行阶段只做“核对 + 必要的失效修复”；除已存在的未提交修复外，不新增 job 或放宽任何阻断项。

### 3.4 `.upgrade/`

| 文件 | 现状 | 改为 |
|---|---|---|
| `.upgrade/STATE.md:27` | 称“当前带日期测试基线为 `1102 passed`”，与 `:58` 的 `1131 passed` 矛盾 | 标注为历史轮次基线，当前基线改为实测值 |
| `.upgrade/STATE.md:5-7,61-67,100-122` | 未记录远端 run 41281614067 的 4 job 失败与根因；`last_validation.subject` 为未提交工作树 | 追加 CI 失败/修复记录；提交后把 `last_validation` 主体改为最终 SHA，测试/CI 状态逐项实际填写；阻塞项保留远端治理项 |
| `.upgrade/MANIFEST.md:57` | “Phase 0-4 全部完成；本地 v1.3.0 tag…” | 改为“Phase 4 进行中（代码侧完成，远端治理待办）；当前 v1.7.0” |
| `.upgrade/MANIFEST.md:55-107` | 决策清单缺 `p1-business-closure-hardening.md`、`DEC-B1811F986E66.json`；`FINAL_REPORT.md` 说“尚未产出”但文件已存在（占位） | 补齐清单行，注明占位不是交付 |
| `.upgrade/docs/UPGRADE_REQUIREMENTS.md` | 空骨架 | 填入 Context / Problems / Outcomes / Scope-Exclusions / Constraints / Success Criteria / Risks-Assumptions / Required Decisions（精简真实内容） |
| `.upgrade/docs/UPGRADE_PLAN.md` | 空骨架 | 填入 P0–P4 阶段、依赖、验收门、回滚、审批门 |
| `.upgrade/docs/IMPLEMENTATION_PLAN.md` | 空骨架 | 填入本次 T1–T9 任务表（状态/证据/阻塞） |
| `.upgrade/validation/records.jsonl` | 最后记录 2026-09-22、版本 1.3.0 | 不手工追加（`subject_digest` 生成语义无法在本地确认，禁止伪造治理证据）；以 `STATE.last_validation` + trace 记录；若执行时可用维护器 CLI，则改用其 validation 命令 |
| `.upgrade/decisions/` | 缺本次决策 | 新增 `doc-ci-alignment-20261101.md`：提交拆分、文档事实来源、不扩展检查脚本、远端未验证项 |
| `.upgrade/plans/` | 无本次计划 | 新增 `2026-11-01-doc-ci-upgrade-alignment.md`（本方案入库副本），并在 MANIFEST 登记 |
| `.upgrade/traces/` | 无本轮 trace | 新增 `20261101T…-doc-ci-alignment.md`，记录实际执行的命令、结果、未执行项 |

## 4. 实施顺序

### Step 0 — 基线与保护（只读）
1. `git status --short` 记录起始状态；确认 `.env` 的 `STORAGE_BACKEND`（不打印密钥）。
2. 禁止运行会覆盖 `.env` 的目标：`make demo-api`、`make demo-ui`、`make e2e-mock`、`make e2e-full-test`。改用显式环境变量运行同一测试集合。

### Step 1 — 文档对齐（提交 2 内容）
按 §3.1、§3.2 顺序修改：`README.md` → `docs/README.md` → `docs/acceptance_report.md` → `docs/startup.md` → `docs/local_setup.md` → spec 5 份 → ISSUE_TEMPLATE。
规则：所有“当前”数字必须在实测后填写；未执行的写“未验证（原因）”；历史段落保留并标注日期/版本。

### Step 2 — CI 核对（提交 1 内容）
1. 核对 `ci.yml` 四个 job、环境变量、阻断/非阻断、动态 head、测试文件列表。
2. 核对 `tests/test_ci_migration_head.py` 覆盖动态 head 与 Alembic 包遮蔽。
3. 仅当发现新的失效配置时修改；不改变阻断级别。

### Step 3 — 本地验证（见 §5）
按顺序：`uv lock --check`（或 `uv sync --all-extras --frozen`）→ `make lint` → `make typecheck` → `make doc-check` → `make version-check` → `make security-check` → 全量 pytest（显式环境变量）→ 可选 Docker lite 冒烟 → `git diff --check`。
失败项先区分“本次改动引入 / 既有实现问题”，后者单独列入清单，不用文档掩盖。

### Step 4 — 提交 1（代码 + CI + 版本）
显式 staging：`core/`、`storage/`、`api/`、`auth/`、`frontend/`、`tests/`、`alembic/`、`scripts/`、`pyproject.toml`、`uv.lock`、`core/version.py`、`CHANGELOG.md`、`.github/workflows/ci.yml`、`.upgrade/decisions/p1-business-closure-hardening.md`。
提交信息建议：`feat(governance): harden business closure and repair CI head assertion (v1.7.0)`。
推送后立刻用 `gh run list --limit 2 --json` 记录该 SHA 的 run ID 与四 job 结论。

### Step 5 — 提交 2（文档 + .upgrade 同步）
显式 staging：`README.md`、`AGENTS.md`、`CLAUDE.md`（如有改）、`docs/`、`.github/ISSUE_TEMPLATE/bug_report.md`、`.upgrade/STATE.md`、`.upgrade/MANIFEST.md`、`.upgrade/docs/`、`.upgrade/decisions/doc-ci-alignment-20261101.md`、`.upgrade/plans/2026-11-01-doc-ci-upgrade-alignment.md`、`.upgrade/traces/…`。
推送并记录该 SHA 的远端 run。

### Step 6 — 提交 3（验证回填，仅文档/升级记录）
把提交 1、2 的 run ID、job 结论、本地检查结果写回 `.upgrade/STATE.md`（不在文件内自引用提交 3 自身结果）。
推送后确认提交 3 的 CI 通过；其自身 run 结论写入最终答复与 trace。

### Step 7 — 收尾
`git status --short` 为空、`git diff --check` 通过、本地 `HEAD == origin/main`；汇总“通过/失败/跳过/未验证”四类结果。

## 5. 逐项验收标准

| # | 检查项 | 命令/证据 | 通过标准 | 失败/不可执行处置 |
|---|---|---|---|---|
| 1 | 依赖锁定 | `uv lock --check` | exit 0；`uv.lock` 与 `pyproject.toml` 一致 | 记录差异，不手改 lock |
| 2 | Lint | `make lint` | `ruff check` 与 `ruff format --check` exit 0 | 归类为实现问题并修复；不写“已通过” |
| 3 | 类型检查 | `make typecheck` | mypy exit 0 | 记录具体文件/行；CI 仍保持 non-blocking 观察期，不擅自转正 |
| 4 | 文档一致性 | `make doc-check` | 0 违规；记录扫描份数（预期 37） | 坏链/target/路径逐条修 |
| 5 | 版本一致性 | `make version-check` | `Version metadata OK: 1.7.0` | 修版本源，不改脚本规则 |
| 6 | 依赖审计 | `make security-check` | exit 0（仅登记过的 advisory 被忽略） | 网络/审计不可用 → 未验证并写明原因 |
| 7 | 全量测试 | 注入 `STORAGE_BACKEND=sqlite`、`CHECKPOINT_BACKEND=memory`、`LLM_MODE=mock` 后 `uv run pytest tests/ -q` | 记录精确 passed/skipped；skip 必须逐条归因（3 个 PG/Redis E2E + 1 个 PG-only） | 任一失败列为实现问题，不在文档中掩盖 |
| 8 | Mock 场景验收 | 直接运行 `tests/test_scenarios_registry.py`、`tests/test_scenario_session_flow.py`、`tests/test_mock_llm_mode.py` | 全部通过 | 不用 `make e2e-mock`（会覆盖 `.env`） |
| 9 | 迁移断言 | `uv run python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; print(ScriptDirectory.from_config(Config('alembic.ini')).get_current_head())"`；`pytest tests/test_ci_migration_head.py` | 输出 `V012`；测试通过；`ci.yml` 无硬编码 `(head)` | 修 `ci.yml`，不改测试以放宽断言 |
| 10 | Docker Lite 冒烟 | `docker compose -f docker-compose.lite.yml up --build -d` + `/health/live` | HTTP 200 | Docker 不可用 → 未验证（原因），委托 CI |
| 11 | 远端 CI（提交 1） | `gh run list --json` 对应 SHA | 四个 job 全部 success；记录 run ID | 失败则修因后新提交，不声明完成 |
| 12 | 远端 CI（提交 2） | 同上 | 四个 job 全部 success | 同上 |
| 13 | 远端 CI（提交 3） | 同上 | 四个 job 全部 success | 同上；其结论写入最终答复 |
| 14 | `.upgrade` 一致性 | `STATE` / `MANIFEST` / 三份计划 / trace 交叉核对 | 版本、迁移头、测试基线、CI 状态、阻塞项与实际一致；无“已完成”与证据冲突 | 维护器 CLI 不可用 → 在 STATE 标注 `unverified` 原因 |
| 15 | 收尾 | `git status --short`、`git diff --check`、`git rev-parse HEAD` / `origin/main` | 工作树 clean；无空白错误；本地与远端同 SHA | 不清理用户未授权文件 |

## 6. 假设与决策

1. **版本口径**：本次发布版本为 `1.7.0`（代码、`pyproject.toml`、`uv.lock`、CHANGELOG、STATE 已一致），不新增 1.8.0。
2. **提交拆分**：用户已确认两次提交并推送；为让提交 1 的 CI 可通过，`ci.yml` 的动态 head 修复归入提交 1，文档与 `.upgrade` 归入提交 2，验证回填归入提交 3。
3. **文档事实来源**：代码/迁移/测试 > 版本元数据 > `docs/spec` 与启动指南 > `.upgrade/STATE.md` > archive。历史归档不重写，只补“已归档/历史”标注。
4. **验收报告处理**：`docs/acceptance_report.md` 保持“当前验收报告”定位，更新当前段并把旧段降级为历史，不新建报告文件。
5. **不扩展检查脚本**：`version_check.py` 只校验 `core/version.py` 与 `pyproject.toml`；不在本次把 README/文档版本纳入自动断言，避免改变验收工具行为。
6. **`.upgrade` 验证记录**：不手写 `records.jsonl`（无法确认 `subject_digest` 语义）；以 `STATE.last_validation` + 追加 trace 记录实际执行结果，并明确未追加原因。
7. **不覆盖本地 `.env`**：所有测试用进程环境变量注入；避免 `make demo-*` / `make e2e-*` 的 `cp -f .env.demo .env`。
8. **CI 阻断级别不变**：mypy 保持 `continue-on-error: true`；`production-safety`、`docker-full-integration`、`docker-lite-integration` 保持阻断。

## 7. 风险与回滚

| 风险 | 处置 |
|---|---|
| 提交 1 的 CI 仍因未知原因失败 | 保留失败 run 证据，按 job/step 定位；必要时追加修复提交；不修改文档宣称通过 |
| 本地全量测试因 `.env` 指向 PostgreSQL 卡住 | 用环境变量覆盖后端；若仍卡住，先确认 `.env` 内容并记录，不改用户 `.env` |
| mypy/pip-audit 出现既有问题 | 单独列为实现问题；mypy 保持观察期，pip-audit 仅接受已登记 advisory |
| `.upgrade` 手工编辑与服务端治理规则冲突 | 只改 STATE/MANIFEST/plans/docs/traces；不碰 `AUTHORITY.json` / `ARTIFACTS.json` / `delivery/POLICY.json`；冲突则上报 |
| Docker/Redis 不可用 | 标记未验证，由 CI `production-safety` 提供最终证据 |

回滚：文档改动可 `git revert <commit>`；`.upgrade` 记录保留追加历史不删除；代码回滚前先按 `storage/README.md` 处理 `goal` 解密或恢复备份。
