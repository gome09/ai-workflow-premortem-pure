# Upgrade Manifest

Defines file lifecycle rules for `.upgrade/`. Update this file whenever files are added, archived, or deleted.

## Always Keep (Permanent Records)

- `.upgrade/STATE.md` — current upgrade state
- `.upgrade/MANIFEST.md` — this file
- `.upgrade/stages/*.md` — phase planning documents
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
| `.upgrade/STATE.md` | active | permanent | 当前升级状态（Phase 0-4 全部完成，v1.2.1） |
| `.upgrade/MANIFEST.md` | active | permanent | 本文件 |
| `.upgrade/decisions/RELEASE_CLEANUP.md` | active | permanent | v1.0 发布前组件清理决策记录（移除/归档了哪些组件及原因），moved from project root 2026-07-13 |
| `.upgrade/decisions/branch-protection.md` | active | permanent | Phase 4 T4.2 main 分支保护策略决策（GitHub 后台手动操作步骤） |
| `.upgrade/decisions/doc-check-stage3-dangling-ref.md` | active | permanent | Phase 4 T4.1 stage3 文档悬空引用补档决策 |
| `.upgrade/decisions/scorecard-baseline.md` | active | permanent | Phase 4 T4.3 Scorecard 基线扫描决策 |
| `.upgrade/reports/release_manifest_v1.0.md` | active | keep-until-superseded | v1.0 生产文件范围清单，moved from project root 2026-07-13 |
| `.upgrade/reports/scorecard-baseline-20260713.md` | active | keep-until-superseded | Phase 4 T4.3 Scorecard 基线报告（2026-07-13 快照） |
| `.upgrade/reports/scorecard-trend-20260714.md` | active | keep-until-superseded | Phase 4 T4.3 Scorecard 趋势报告（基线对照 + 18 项预期变化） |
| `.upgrade/reports/nist-ai-600-1-action-summary.md` | active | keep-until-superseded | Phase 2 T2.2 NIST AI 600-1 动作项映射摘要（4 项标存疑） |
| `.upgrade/reports/tc260-agent-deployment-summary.md` | active | keep-until-superseded | Phase 2 T2.4 TC260 智能体部署使用安全指引映射摘要 |

## Moved from Project

> This section is populated by Mode 4 (Project Scan). Each row records a file moved from the project into `.upgrade/`.

| Original Path | New Path | Reason | Risk | Follow-up Needed |
|---|---|---|---|---|
| `RELEASE_CLEANUP.md` | `.upgrade/decisions/RELEASE_CLEANUP.md` | 记录 v1.0 发布前组件移除/归档决策及理由，属于升级/清理过程记录，非当前产品文档 | medium (referenced only by `docs/plan/improvement-roadmap.md` prose mention, no machine refs) | 如后续文档引用该路径需更新链接 |
| `docs/improvement-roadmap.md` | `docs/plan/improvement-roadmap.md` | docs/ 拆分 plan/spec 子目录，路线图归入 plan/ | low (internal docs reorg, references updated in docs/README.md/CLAUDE.md/.upgrade/) | 无 |
| `docs/architecture.md` | `docs/spec/architecture.md` | docs/ 拆分 plan/spec 子目录，架构设计文档归入 spec/ | low | 无 |
| `docs/security-model.md` | `docs/spec/security-model.md` | docs/ 拆分 plan/spec 子目录，安全模型文档归入 spec/ | low | 无 |
| `docs/stage3-risk-adaptive-gate.md` | `docs/spec/stage3-risk-adaptive-gate.md` | docs/ 拆分 plan/spec 子目录，门禁设计文档归入 spec/ | low | 文件内引用 `archive/verification-reports/risk_adaptive_gate_final_validation.md` 已同步改为 `../archive/...`，但该目标文件本身在仓库中不存在（既有悬空引用，非本次移动引入） |
| `docs/api-reference.md` | `docs/spec/api-reference.md` | docs/ 拆分 plan/spec 子目录，API 参考文档归入 spec/ | low | 无 |
| `release_manifest_v1.0.md` | `.upgrade/reports/release_manifest_v1.0.md` | v1.0 生产文件范围快照，属于一次性发布报告，非持续维护文档 | low (no refs found) | 无 |
