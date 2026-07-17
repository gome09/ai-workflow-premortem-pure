# Upgrade Manifest

Defines file lifecycle rules for `.upgrade/`. Update this file whenever files are added, archived, or deleted.

## Always Keep (Permanent Records)

- `.upgrade/STATE.md` — current upgrade state
- `.upgrade/MANIFEST.md` — this file
- `.upgrade/plans/*.md` — phase/wave planning documents（本工作区以 `plans/` 承担标准结构中 `stages/` 的角色）
- `.upgrade/reports/FINAL_REPORT.md` — final upgrade report
- `.upgrade/decisions/*.md` — all decision records
- `.upgrade/reviews/*.md` — all review records

## Keep Until Phase Complete (Discard After)

- `.upgrade/reports/stageN_report.md` — may archive after superseded by FINAL_REPORT

## Archive After Completion

- Outdated draft files (e.g., UPGRADE_DRAFT.md after plan is confirmed)
- Superseded plan versions
- Old STATE.md snapshots

Target: `.upgrade/archive/<original-filename>`

## Never Commit

- `.upgrade/tmp/` — all contents
- `.upgrade/cache/` — all contents
- `*.tmp` anywhere under `.upgrade/`
- `*.bak` anywhere under `.upgrade/`

## Delete After Phase Cleanup

- Raw execution logs (after compression or review)
- One-time analysis scripts that have no reuse value
- Duplicate drafts after merge

## Cleanup Classification Reference

Before cleanup, classify each file as one of:

| Label | Action |
|---|---|
| `keep` | Leave in place, no change |
| `update` | Refresh content, keep file |
| `merge` | Consolidate into STATE.md, reports/, or decisions/ |
| `archive` | Move to `.upgrade/archive/` |
| `delete` | Remove permanently |
| `confirm` | Requires human decision before acting |

## File Inventory

| File | Status | Lifecycle | Notes |
|---|---|---|---|
| `.upgrade/STATE.md` | active | permanent | 当前升级状态（Phase 0-4 全部完成；formal-project-uplift Wave A–E 全部完成，v1.3.0 已发布待公开） |
| `.upgrade/MANIFEST.md` | active | permanent | 本文件 |
| `.upgrade/decisions/RELEASE_CLEANUP.md` | active | permanent | v1.0 发布前组件清理决策记录（移除/归档了哪些组件及原因），moved from project root 2026-07-13 |
| `.upgrade/decisions/branch-protection.md` | active | permanent | Phase 4 T4.2 main 分支保护策略决策（GitHub 后台手动操作步骤） |
| `.upgrade/decisions/doc-alignment-and-frontend-polish.md` | active | permanent | 文档-代码对齐 + 前端中文化收尾（demo 可运行性打磨）决策，commit 545c827 |
| `.upgrade/decisions/doc-check-stage3-dangling-ref.md` | active | permanent | Phase 4 T4.1 stage3 文档悬空引用补档决策 |
| `.upgrade/decisions/scorecard-baseline.md` | active | permanent | Phase 4 T4.3 Scorecard 基线扫描决策 |
| `.upgrade/archive/release_manifest_v1.0.md` | archived | archive | v1.0 生产文件范围清单（已被 v1.3.0 取代），moved from project root 2026-07-13，2026-07-17 Mode 3 归档 |
| `.upgrade/archive/scorecard-baseline-20260713.md` | archived | archive | Phase 4 T4.3 Scorecard 基线报告（2026-07-13 快照，数据已被趋势报告吸收），2026-07-17 Mode 3 归档 |
| `.upgrade/reports/scorecard-trend-20260714.md` | active | keep-until-superseded | Phase 4 T4.3 Scorecard 趋势报告（基线对照 + 18 项预期变化） |
| `.upgrade/reports/nist-ai-600-1-action-summary.md` | active | keep-until-superseded | Phase 2 T2.2 NIST AI 600-1 动作项映射摘要（4 项标存疑） |
| `.upgrade/reports/tc260-agent-deployment-summary.md` | active | keep-until-superseded | Phase 2 T2.4 TC260 智能体部署使用安全指引映射摘要 |
| `.upgrade/reports/mypy-baseline-20260717.md` | active | keep-until-superseded | Wave B mypy 基线报告（宽松档 108 → 0 清零记录；raw 干跑输出在 `.upgrade/tmp/`，gitignored 仅本地留存） |
| `.upgrade/reports/standard-tracking-2026-07-14.md` | active | keep-until-superseded | 外部标准动态跟踪记录（未成年人指南 2026-08-16 截止 / TC260 / NIST / OWASP ASI），STATE.md Required Context File；2026-07-17 Mode 3 自 gitignored 的 `logs/` 移入 reports/ 纳入版本控制 |
| `.upgrade/research/benchmarking-20260716/` | active | keep-until-superseded | 对标调研原始数据快照（deepeval / guardrails-ai / inspect_ai / NeMo-Guardrails 的 GitHub repo/releases API 采集 + README 快照；tags 快照仅 deepeval 与 inspect_ai 两家，采集日 2026-07-16），供开源门面对齐与竞品定位分析引用；2026-07-17 Mode 3 删除冗余截断副本 `readme_deepeval.md`（为 `readme_deepeval_full.md` 的前缀截断） |
| `.upgrade/plans/2026-07-17-formal-project-uplift.md` | active | permanent | 正式项目升级主计划（Wave A–E，Task 0–19，目标 v1.3.0） |
| `.upgrade/plans/2026-07-17-wave-a-implementation.md` | active | permanent | Wave A 具体实施计划（探索核实修正版：A5/A6 顺序对调、MANIFEST 表格格式、README 锚点） |
| `.upgrade/plans/2026-07-17-wave-b-mypy-implementation.md` | active | permanent | Wave B mypy 渐进式类型检查实施计划（B1–B6 分片，inspect_ai 模式宽松档 + core.gates/graph 近 strict） |
| `.upgrade/plans/2026-07-17-wave-c-llm-judge-implementation.md` | active | permanent | Wave C T3.6 LLM Judge 实施计划（C1–C4，含 18 条探索基线与两处对父计划的记录性偏差决策） |
| `.upgrade/plans/2026-07-17-wave-d-compliance-refresh-implementation.md` | active | permanent | Wave D 合规映射复核落账实施计划（D1–D3，含 17 条探索基线与三处对父计划的记录性偏差决策：ISO 附录编号 §6 / TC260 [信源说明] 措辞修正 / §10.7 插入尾注前） |
| `.upgrade/reports/pre-publication-checklist-20260717.md` | active | keep-until-superseded | Wave E 公开前安全扫描报告（三项检查通过 + 已知良性命中判定留档 + 公开后 10 步人工动作清单 + CI 门槛转正评估结论） |
| `.upgrade/plans/2026-07-17-wave-e-publication-ci-implementation.md` | active | permanent | Wave E 公开前检查与 CI/发布收尾实施计划（E1–E4 + 附录 E5，含 20 条探索基线与六处对父计划的记录性偏差决策） |
| `.upgrade/archive/show.md` | archived | archive | v1.0 时期项目展示文档（毕设介绍），内容已被 README.md (v1.3.0) 取代且无任何文件引用，moved from project root 2026-07-17 |

## Moved from Project

> This section is populated by Mode 4 (Project Scan). Each row records a file moved from the project into `.upgrade/`.

| Original Path | New Path | Reason | Risk | Follow-up Needed |
|---|---|---|---|---|
| `RELEASE_CLEANUP.md` | `.upgrade/decisions/RELEASE_CLEANUP.md` | 记录 v1.0 发布前组件移除/归档决策及理由，属于升级/清理过程记录，非当前产品文档 | medium (referenced only by `docs/plan/improvement-roadmap.md` prose mention, no machine refs) | 如后续文档引用该路径需更新链接 |
| `docs/improvement-roadmap.md` | `docs/plan/improvement-roadmap.md` | docs/ 拆分 plan/spec 子目录，路线图归入 plan/ | low (internal docs reorg, references updated in docs/README.md/CLAUDE.md/.upgrade/) | 无 |
| `docs/architecture.md` | `docs/spec/architecture.md` | docs/ 拆分 plan/spec 子目录，架构设计文档归入 spec/ | low | 无 |
| `docs/security-model.md` | `docs/spec/security-model.md` | docs/ 拆分 plan/spec 子目录，安全模型文档归入 spec/ | low | 无 |
| `docs/stage3-risk-adaptive-gate.md` | `docs/spec/stage3-risk-adaptive-gate.md` | docs/ 拆分 plan/spec 子目录，门禁设计文档归入 spec/ | low | ~~悬空引用~~ 已由 stage3 补档决策修复（`docs/archive/verification-reports/risk_adaptive_gate_final_validation.md` 现已存在，见 `.upgrade/decisions/doc-check-stage3-dangling-ref.md`） |
| `docs/api-reference.md` | `docs/spec/api-reference.md` | docs/ 拆分 plan/spec 子目录，API 参考文档归入 spec/ | low | 无 |
| `release_manifest_v1.0.md` | `.upgrade/reports/release_manifest_v1.0.md` | v1.0 生产文件范围快照，属于一次性发布报告，非持续维护文档 | low (no refs found) | 2026-07-17 Mode 3 再归档至 `.upgrade/archive/` |
| `show.md` | `.upgrade/archive/show.md` | v1.0 时期项目展示/答辩文档，与 README 大量重叠且版本号落后（v1.0 vs v1.3.0），全仓无引用，已被 README.md 取代 | low (no refs found; git mv 保留历史) | 无（2026-07-17 Mode 4 扫描归档） |
| `artifacts_live_e2e.log` | `.upgrade/logs/artifacts_live_e2e.log` | live E2E 四阶段实跑日志（RESULT: PASS），一次性运行产物，本就被 `.gitignore` `*.log` 忽略 | low (no refs; untracked) | 无（`.upgrade/logs/` gitignored，仅本地留存） |
