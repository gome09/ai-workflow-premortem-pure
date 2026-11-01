# Upgrade Requirements

## Context

AI Workflow Premortem 的代码侧已推进到 v1.7.0（Alembic V012 / ProjectContext `0.10.0`），但根文档、`docs/`、GitHub Actions 与 `.upgrade/` 仍混有旧版本、旧迁移头和未经验证的完成声明。远端 `main` 最新提交 `16624b9` 的 CI（run 41281614067）四个 job 全部失败，且本地 v1.7.0 改动尚未提交推送。

## Problems

1. `README.md` 仍标注 `v1.3.0`；`docs/acceptance_report.md` 的“当前基线”仍是 v1.3.0 / `800 passed` / `V001→V008` / doc-check 38 份。
2. `docs/spec/supply-chain-security.md` 声称 pip-audit 为 `continue-on-error`、CI 只有三个 job，与当前 Makefile / `ci.yml` 不一致。
3. `.upgrade/STATE.md` 同时存在 `1102 passed` 与 `1131 passed` 两个“当前”基线；`.upgrade/MANIFEST.md` 声称 Phase 0–4 全部完成且当前 v1.3.0。
4. `.upgrade/docs/UPGRADE_REQUIREMENTS.md`、`UPGRADE_PLAN.md`、`IMPLEMENTATION_PLAN.md` 仅有空章节骨架。
5. 远端 CI 失败根因：`ruff check` 2 处、`core.coverage` 未入库（`.gitignore` 未锚定 `coverage/`）、迁移断言硬编码 `V010 (head)`。

## Outcomes

- 根文档、当前规格、启动指南统一到 `1.7.0` / Alembic `V012` / ProjectContext `0.10.0`。
- CI 与文档声明一致：四个 job；`make lint` 阻断；`make audit` 为 non-blocking 观察步骤；迁移 head 由 `ScriptDirectory.get_current_head()` 动态计算。
- `.upgrade` 的状态、任务、计划、清单、验证记录与实际执行证据一致，历史条目明确标注为历史。

## Scope / Exclusions

范围内：文档对齐、CI 配置核对与失效修复、`.upgrade` 同步、提交与远端验证。
范围外：业务功能扩展、依赖大版本升级、改写 `docs/archive/**` 与 `.upgrade/archive/**`、伪造或补造未执行检查、GitHub 后台治理设置。

## Constraints

- 事实来源优先级：代码/迁移/测试 > `core/version.py` / `pyproject.toml` / Alembic > `docs/spec` 与启动指南 > `.upgrade/STATE.md` > archive。
- 测试基线必须使用项目 `.venv`，环境为 `STORAGE_BACKEND=sqlite` + `CHECKPOINT_BACKEND=memory` + `LLM_MODE=mock`。
- 不覆盖用户 `.env`；不执行 `git add .`；推送已获用户批准。
- 远端 CI 结果必须引用 run ID 与 SHA；无法执行的检查标注 `unverified` 及原因。

## Success Criteria

- `version-check`、`doc-check`、Ruff lint/format、mypy、全量 pytest 通过，并记录精确 passed/skipped。
- 提交 1/2/3 在同一 SHA 上的 GitHub Actions 四个 job 全部 success（无法执行时明确不声明完成）。
- `.upgrade` 中不存在与实测证据冲突的“已完成”声明。

## Risks / Assumptions

- 外部 advisory 库持续漂移：2026-11-01 实测 124 条 unique advisory / 19 个包；pillow（streamlit `pillow<13`）、ecdsa（无修复）、`langgraph-checkpoint-postgres`（V006 固定 `3.0.5`）暂不可升级。
- 本地 Docker daemon 与 Redis 未运行，Docker/Redis E2E 由 CI 提供唯一可执行证据。
- 当前 Windows 环境未安装 GNU make，验收命令以底层等价命令执行并注明。

## Required Decisions

- 提交拆分与推送：用户已批准（两次提交 + 一次验证回填，均推送并等待远端 CI）。
- 依赖审计策略：用户已批准（CI 中 lint 阻断、audit non-blocking；本地 `make security-check` 保持严格）。
- `.upgrade` 计划文档：用户已批准填入精简真实内容。
