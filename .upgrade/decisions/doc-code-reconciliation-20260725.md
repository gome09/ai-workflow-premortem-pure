# 文档与业务代码一致性整理决策（2026-07-25）

## 判定原则

- 运行时代码、配置、迁移注册表和可执行测试是当前事实来源。
- 明确带日期与版本的验收数字作为历史证据保留，不改写成当前结果。
- 当前使用指南不得继续引用已失效的迁移终点、CI 状态或测试数量。
- 设计计划与实施计划虽包含历史代码片段，但承担决策追溯职责，不按“重复文档”删除。

## 本轮处理

| 对象 | 结论 | 操作与依据 |
|---|---|---|
| `storage/README.md` | 矛盾 | 更新 Alembic 迁移终点 V003 → V005；依据 `alembic/versions/`。 |
| `core/migrations/README.md` | 矛盾/失效 | 更新当前 schema 0.7.0 → 0.9.0，并补齐两段迁移链；依据 `core/migrations/registry.py`。 |
| `scripts/README.md`、`scripts/archive/README.md` | 矛盾/失效 | doc-check 已是 CI 阻断步骤，移除“non-blocking”旧描述；归档说明不再把 v1.0 说成当前版本，并同步当前版本事实为 v1.3.0。 |
| `docs/startup.md`、`docs/local_setup.md` | 矛盾 | 当前全量测试实测为 623 passed, 8 skipped；历史 650/1 仅保留在有日期的验收快照中。 |
| `docs/acceptance_report.md` | 信息缺口 | 新增 2026-07-25 当前代码基线，不覆盖 2026-07-17/18 历史验收证据。 |
| 安全、PIA 与运维文档 | 矛盾 | 字段加密改为“代码支持但默认部署未启用”；留存天数改为“声明性配置、无自动清理”；修正不存在的 Docker volume snapshot/Loki 能力。 |
| `docs/plan/phase-*.md` | 状态失效 | 保留决策追溯价值，不删除；统一在文首标记为已完成的历史基线，当前事实指向 spec/代码/STATE。 |
| `CONTRIBUTING.md` | 状态矛盾 | 本地无法证明远端分支保护已开启，按 `.upgrade/STATE.md` 修正为待维护者执行。 |
| `scripts/doc_consistency_check.py` | 覆盖不足 | 扫描范围扩展为全部当前项目 Markdown，排除 `.upgrade/` 历史记录、运行时产物与缓存，防止根目录/组件 README 再次漂移。 |
| `README.md` | 局部重复 | 答辩章节不再重复一套离线启动命令，改为链接到唯一快速开始入口。 |
| `artifacts/live_e2e_four_stage/session_export.md` | 冗余/失效 | 删除未跟踪的运行时导出；其内容是 v1.2.2 会话 JSON 包装且无仓库引用，正式验收结论已由 `docs/acceptance_report.md` 和 `.upgrade/reports/startup-methods-e2e-20260718.md` 承担。 |
| `docs/plan/*.md` | 保留并降级为历史记录 | 属于决策追溯材料，且被 `docs/README.md` / `.upgrade/STATE.md` 明确索引；增加历史基线提示，避免旧行号与旧版本被误认成当前事实。 |
| `docs/lite-mode.md` | 保留 | 与 startup/local_setup 有少量命令重叠，但其价值是 SQLite 后端边界和代码对应关系，不属于无效重复。 |

## 验证

- `python scripts/doc_consistency_check.py`
- `python scripts/version_check.py`
- `python -m pytest tests/ -q`
- `git status --short`

## 2026-07-27 深度复核增补

- 4 个只读子代理分别覆盖 spec、运行部署、全仓 Markdown 清单和安全合规；主代理以当前代码、workflow、配置与测试复核。
- 进一步修正默认 `single_step` / SQLite 架构路径、供应链 workflow 当前态、治理 Gauge 占位状态、Stage 3 安全发现条件、Context 迁移删除条件和本地真实模式 secrets provisioning。
- 收窄 PII 能力边界：当前掩码只覆盖 evidence/user_materials 格式化路径，直接消息与历史不覆盖；心理健康示例不含四类正则 PII，不会自动升级为 `sensitive_personal`；平台也没有独立的告知同意记录机制。
- 删除 `scripts/archive/` 下 3 个已失效脚本：两个旧 live E2E 缺少认证、对当前 API 必然 401；alpha 审计脚本硬编码旧版本和不存在路径。三者无 Makefile/CI/生产/测试调用，可从 Git 历史恢复。保留一次性 tenant 回填脚本。
- 未发现适合整份删除或合并的 Markdown：spec、PIA、运行手册、代码旁 README 与 plan 历史基线职责不同；重复内容通过摘要/互链和边界说明处理。
- 验证：doc consistency 51 份 Markdown / 0 违规；version 1.3.0 一致；pytest 623 passed / 8 skipped；`git diff --check` 通过。Windows 当前无 `make` 可执行文件，使用 Makefile 中对应的 Python 底层命令。
