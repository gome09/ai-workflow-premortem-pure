# Upgrade State

## Current Phase

Phase 0 — Not started (detailed plans for all phases now authored; ready to execute)

## Current Task

None in flight. Next executable work is Phase 0 tasks per `docs/plan/phase-0-repo-governance.md` (T0.1 LICENSE decision is user-blocked; T0.2–T0.8 are unblocked).

## Last Completed

- **Design-plan authoring pass (2026-07-13, this session)**: expanded `docs/plan/improvement-roadmap.md` into a full plan/spec document set based on verified project state (5 parallel exploration agents over repo governance, taxonomy, storage/privacy, gates/auth/observability, docs) plus fresh external-standard verification via web search:
  - New plan files: `docs/plan/phase-0-repo-governance.md`, `phase-1-security-compliance.md`, `phase-2-risk-taxonomy.md`, `phase-3-governance-platform.md`, `phase-4-community.md`.
  - New spec files (all `Status: Designed, not implemented`): `docs/spec/supply-chain-security.md`, `data-classification-and-privacy.md`, `risk-taxonomy-engine.md`, `governance-platform.md`.
  - `improvement-roadmap.md`: added §10 复核增补 (EU AI Act Omnibus new dates; OWASP Agentic ASI 2026; NIST agent initiatives; TC260 智能体部署使用安全指引 published — roadmap §8 question 2 resolved; factual correction: `university_mental_health` does NOT auto-escalate to HIGH, lands MEDIUM per `core/gates/risk_profile.py` keyword tables) + per-phase plan links.
  - Updated `docs/README.md` index and `CLAUDE.md` 文档维护 section (outside controlled block, per explicit user request).
- Earlier same day: Mode 1 init + Mode 4 scan/move + CLAUDE.md creation + docs/ split into plan/spec (see git history).

## Required Context Files

- `.upgrade/MANIFEST.md`
- `docs/plan/improvement-roadmap.md` — roadmap; §10 supersedes conflicting body text
- `docs/plan/phase-0-repo-governance.md` … `phase-4-community.md` — per-phase executable plans with acceptance checklists
- `docs/spec/{supply-chain-security,data-classification-and-privacy,risk-taxonomy-engine,governance-platform}.md` — design-state specs backing the plans

## Blockers

- Phase 0 T0.1 (LICENSE) blocked on user decision: MIT / Apache 2.0 / AGPL-3.0 (roadmap §8 question 1).
- Phase 3 T3.6 (LLM Judge) gated on user confirming real demand for automated evaluation (roadmap §8 preserved condition).

## Active Stage Report

None.

## Validation Commands

- `git status --short`
- `git diff`
- `make lint` / `make test` (unchanged by this docs-only pass)

## Next Action

Execute Phase 0 unblocked tasks (T0.2 SECURITY.md, T0.3 CONTRIBUTING.md, T0.4 CI permissions, T0.5 dependabot.yml, T0.6 CHANGELOG traceability note, T0.8 git tag), then T0.7 Scorecard baseline; ask user for LICENSE decision when convenient.

## Last Updated

- Date: 2026-07-13
- By: claude-code
- Summary: Authored full plan/spec design set (5 phase plans + 4 specs), roadmap §10 external-standards re-verification addendum, index/CLAUDE.md updates.
