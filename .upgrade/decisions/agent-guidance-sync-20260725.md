# AGENTS.md / CLAUDE.md 同步决策（2026-07-25）

## 背景

仓库级代理说明仍停留在 Phase 0–4 执行前后的混合状态：`AGENTS.md` 只有升级受控块，`CLAUDE.md` 仍把项目简化为本科毕业设计，并要求继续按历史 phase 计划勾选任务。与此同时，真实代码与 `.upgrade/STATE.md` 已进入 v1.3.0、Phase 0–4 完成后的维护阶段。

## 决策

- `AGENTS.md` 作为所有编码代理的仓库级权威入口，补充当前版本、事实来源优先级、架构不变量、验证命令、安全边界与升级规则。
- 保留 `project-upgrade` 受控块原文，不修改其语义。
- `CLAUDE.md` 改为 Claude Code 补充说明，并显式服从 `AGENTS.md`。
- Phase 0–4 文档统一视为历史计划；新的升级计划进入 `.upgrade/plans/`，当前状态进入 `.upgrade/STATE.md`。
- 明确两项容易被文档夸大的边界：字段加密默认不启用；留存配置没有自动清理执行器。
- CI 当前状态写实：doc-check blocking，mypy 与 docker-full integration non-blocking。

## 当前基线

- App / report schema / package stage: 1.3.0
- Alembic head: V005
- ProjectContext schema: 0.9.0
- Latest local test baseline: 623 passed, 8 skipped（2026-07-25）
- Doc check: 51 current Markdown files, 0 violations
