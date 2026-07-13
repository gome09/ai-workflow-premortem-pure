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
| `.upgrade/STATE.md` | active | permanent | |
| `.upgrade/MANIFEST.md` | active | permanent | |
| `.upgrade/decisions/RELEASE_CLEANUP.md` | active | permanent | v1.0 发布前组件清理决策记录（移除/归档了哪些组件及原因），moved from project root 2026-07-13 |
| `.upgrade/reports/release_manifest_v1.0.md` | active | keep-until-superseded | v1.0 生产文件范围清单，moved from project root 2026-07-13 |

## Moved from Project

> This section is populated by Mode 4 (Project Scan). Each row records a file moved from the project into `.upgrade/`.

| Original Path | New Path | Reason | Risk | Follow-up Needed |
|---|---|---|---|---|
| `RELEASE_CLEANUP.md` | `.upgrade/decisions/RELEASE_CLEANUP.md` | 记录 v1.0 发布前组件移除/归档决策及理由，属于升级/清理过程记录，非当前产品文档 | medium (referenced only by `docs/improvement-roadmap.md` prose mention, no machine refs) | 如后续文档引用该路径需更新链接 |
| `release_manifest_v1.0.md` | `.upgrade/reports/release_manifest_v1.0.md` | v1.0 生产文件范围快照，属于一次性发布报告，非持续维护文档 | low (no refs found) | 无 |
