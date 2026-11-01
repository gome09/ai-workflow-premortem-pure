# Upgrade Plan

Based on `UPGRADE_REQUIREMENTS.md`.

## Phases

| Phase | 内容 | 状态 |
|---|---|---|
| P0 基线核对 | 版本 / 迁移头 / schema / Git 状态 / 本地检查 / 远端 run 41281614067 逐 job 定位 | 完成 |
| P1 CI 根因修复 | `core/coverage/**` 入库与忽略锚定（`7966f9d`）、动态 Alembic head、`test_postgres_p1_storage.py` 纳入 production-safety、审计拆为 non-blocking | 完成（待同 SHA 远端验证） |
| P2 文档对齐 | README / docs 索引 / 验收报告 / 启动指南 / spec / ISSUE_TEMPLATE | 完成（本地） |
| P3 `.upgrade` 同步 | STATE / MANIFEST / 三份计划 / 决策 / trace | 完成 |
| P4 提交与远端验收 | 提交 1/2/3 推送，核对每个 SHA 的四个 job | 进行中（代码提交 `3316bb5` / run 41298061928 全绿；文档提交待验证） |

## Dependencies

- `gh` 已认证（gome09），SSH 推送可用。
- CI 自带 PostgreSQL 16 / Redis 7 service；本地 Docker daemon 不可用、Redis 未运行。
- 外部 advisory 库网络可达；本地 `make audit` 预期失败（已登记为观察项）。

## Acceptance Gates

1. 本地：`version-check`、`doc-check`、Ruff lint/format、mypy、全量 pytest 全部通过（或明确记录失败原因）。
2. 远端：提交 1/2/3 对应 run 的 `lint-and-unit-tests`、`docker-lite-integration`、`production-safety`、`docker-full-integration` 全部 success。
3. 收尾：`git status --short` 为空；本地 `HEAD == origin/main`；`git diff --check` 通过。

## Rollback

- 文档与升级记录：`git revert <commit>`，`.upgrade` 历史记录只追加不删除。
- 代码回滚到 1.7.0 之前：先按 `storage/README.md` 对 `goal` 执行解密或恢复备份。
- CI 回滚：恢复 `ci.yml` 的阻断审计配置前必须先分诊 advisory 或获得新的用户决策。

## Approval Gates

- 推送 main：已由用户明确批准（分两次提交 + 验证回填）。
- 分支保护、Private vulnerability reporting、CodeQL required check、GitHub Release：需维护者在 GitHub 后台执行，未完成前不得宣称已发布。
