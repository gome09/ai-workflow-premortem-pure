# Implementation Plan

Scope: `doc-ci-upgrade-alignment`（2026-11-01）
Plan source: `.upgrade/plans/2026-11-01-doc-ci-upgrade-alignment.md`

| ID | Task | Status | Evidence |
|---|---|---|---|
| T1 | 基线核对（Git / `.env` / Docker） | 完成 | `HEAD=7966f9d`，`origin/main=16624b9`，49 modified + 11 untracked；`.env` 指向 postgres/langgraph/real；Docker daemon 未运行 |
| T2 | 本地验证 | 完成 | `ruff check` 0；`ruff format --check` 392 files；mypy 199 files 0 issue；doc-check 37/0；version-check 1.7.0；pytest `1131 passed, 4 skipped`（72.73s）；`make audit` 失败：124 unique advisory / 19 包 |
| T3 | CI 配置修复与核对 | 完成 | `ci.yml` 动态 head；新增 `test_postgres_p1_storage.py`；lint 阻断 + audit non-blocking；`tests/test_ci_migration_head.py` 覆盖 |
| T4 | 根文档与指南对齐 | 完成 | README 1.7.0 + 能力边界 + 测试节；docs/README；acceptance_report 当前基线 + 历史段；startup/local_setup |
| T5 | 当前规格对齐 | 完成 | governance-platform Status/日期；security-model 邀请与 RBAC；supply-chain 四 job / CodeQL / audit；architecture V009–V012；api-reference 路由数 100 |
| T6 | `.upgrade` 同步 | 完成 | STATE / MANIFEST / 三份计划 / 决策 / trace |
| T7 | 提交 1 推送与远端 CI | 完成 | `cd19398` / `6118649` / `3316bb5`；run 41298061928 四 job success，CodeQL success |
| T8 | 提交 2 推送与远端 CI | 进行中 | 文档 + `.upgrade` 待提交 |
| T9 | 提交 3 验证回填 | 待执行 | 写入提交 2 的 run ID 与结论 |
