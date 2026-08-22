# AGENTS.md

本文件适用于整个仓库，是当前事实基线、常用命令、架构不变量与安全边界的**唯一权威源**。所有编码代理在修改代码、文档、配置或升级记录前，应先遵守本文件。

`CLAUDE.md` 是面向 Claude Code 的补充说明，不得与本文件冲突，也**不重复**本文件已有的可漂移事实——它只承载三块本文件未覆盖的内容：目录结构表、Ruff/pytest 细则、`docs/spec/` 状态清单。新增可漂移事实（版本号、测试基线、CI 状态、能力边界）一律只写入本文件。

## 项目现状

- 项目：AI Workflow Premortem，AI 工作流预验尸与人机监督平台；源于本科毕业设计，当前按长期维护的开源项目演进。
- 当前应用版本：`1.3.0`；版本元数据必须同时保持 `core/version.py` 与 `pyproject.toml` 一致。
- 当前数据库迁移头：Alembic `V005`；当前 `ProjectContext` schema：`0.9.0`。
- Phase 0–4 代码侧已完成；`docs/archive/plan/phase-*.md` 与 `phase-*-design.md` 是历史实施/设计基线（已归档），不得把其中旧版本、旧行号或未勾选项当作当前事实。
- formal-project-uplift Wave A–E 已完成；剩余工作主要是仓库公开后的远端治理动作，如 CodeQL 转正、main 分支保护和发布设置。权威状态见 `.upgrade/STATE.md`。
- 最近一次本地全量测试基线：`660 passed, 1 skipped`（2026-07-31，`make test` 即 `uv run pytest tests/`）。测试数量会随测试集合变化，不应硬编码为永久断言。
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

- `make doc-check` 当前是 CI 阻断项，扫描 50 份当前项目 Markdown（排除 `.upgrade/`、archive、运行时产物和缓存）。
- CI 中 mypy 与 docker-full integration 仍处观察期，当前为 non-blocking；不要在文档中写成已强制。
- 离线开发优先使用 `make demo-api` + `make demo-ui`（Mock LLM + SQLite）。
- Docker Lite 使用 `make lite-up`；完整栈使用 `make setup` + `make prod-up`。

## 架构不变量

- 状态转换由确定性代码控制，LLM 只生成分析内容，不决定流程跳转。
- 默认执行路径是 `single_step`；`langgraph_interrupt` 是实验性 opt-in 路径。
- 高风险推进必须经过风险自适应门禁和必要的 `PendingHumanAction`。
- API 路由只做协议适配，核心逻辑应位于 `core/`、`graph/`、`stages/` 或 `storage/`。
- PostgreSQL schema 迁移只通过 Alembic；`core/migrations/` 仅用于历史 `ProjectContext` JSON 升级，二者不得混用。
- 门禁规则新增/删除时必须同步 `core/gates/rules/manifest.py`、相关测试与规格文档。
- 新增场景时同步 `scenarios/manifests/`、example input、domain profile/mock fixture（如需要）及场景测试。

## 当前安全与合规边界

- 字段加密代码已实现，但 `make setup` 不生成 `DATA_ENCRYPTION_KEY`；未配置时 PostgreSQL 会告警并继续明文存储。生产文档必须要求检查 `/health.data_encryption == enabled`。
- `AUDIT_RETENTION_DAYS` 与 `SESSION_RETENTION_DAYS` 当前仅是配置和健康检查展示，尚无自动清理调度器，不得宣称已自动执行留存策略。
- `PII_MASK_BEFORE_LLM` 默认关闭；涉及真实个人信息的场景必须明确部署侧启用责任。
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
