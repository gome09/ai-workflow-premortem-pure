# Upgrade State

## Current Phase

Phase 0 — Not started

## Current Task

Awaiting definition of Phase 0 upgrade requirements (see `docs/plan/improvement-roadmap.md` for candidate scope: 仓库治理 → 安全合规硬缺口 → AI 风险分类补强 → 治理平台化 → 社区打磨).

## Last Completed

- Mode 1: Initialized `.upgrade/` workspace, created `AGENTS.md` (no prior AI authority files found).
- Mode 4: Scanned project root, moved 2 confirmed candidates into `.upgrade/`:
  - `RELEASE_CLEANUP.md` → `.upgrade/decisions/RELEASE_CLEANUP.md`
  - `release_manifest_v1.0.md` → `.upgrade/reports/release_manifest_v1.0.md`
  - `show.md` reviewed and kept in project root per user decision (not an upgrade-process file).
- Created `CLAUDE.md` at project root with project conventions + Upgrade Workspace Rules controlled block.
- Restructured `docs/` into `docs/plan/`（improvement-roadmap.md）and `docs/spec/`（architecture.md, security-model.md, stage3-risk-adaptive-gate.md, api-reference.md）via `git mv`; updated all cross-references in `docs/README.md`, `CLAUDE.md`, `.upgrade/MANIFEST.md`, `.upgrade/STATE.md`.

## Required Context Files

- `.upgrade/MANIFEST.md`
- `docs/plan/improvement-roadmap.md` — 分阶段改进路线图（中国监管合规 / 国际标准 / 开源工程健康度三条坐标轴，阶段0-4 任务清单）
- `.upgrade/stages/` — phase planning documents (when created)

## Blockers

None.

## Active Stage Report

None.

## Validation Commands

- `git status --short`
- `git diff`

## Next Action

Define Phase 0 requirements doc (`.upgrade/stages/phase0-requirements.md`) scoping which items from `docs/plan/improvement-roadmap.md` 阶段0（仓库治理）to tackle first.

## Last Updated

- Date: 2026-07-13
- By: claude-code
- Summary: Mode 1 init + Mode 4 scan/move (RELEASE_CLEANUP.md, release_manifest_v1.0.md) + CLAUDE.md created + docs/ split into plan/spec.
