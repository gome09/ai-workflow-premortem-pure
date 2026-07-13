# Upgrade State

## Current Phase

Phase 0 — Batch 1 complete (T0.1–T0.6, T0.8 done); T0.7 OpenSSF Scorecard baseline pending.

## Current Task

T0.7 OpenSSF Scorecard baseline scan (serial, last Phase 0 task). Requires `scorecard` CLI + GitHub PAT (or public-repo anonymous mode). Not yet started.

## Last Completed

- **Phase 0 Batch 1 execution (2026-07-13, this session)** — Implemented Phase 0 repo governance baseline per `docs/plan/phase-0-design.md` (this session's design layer). User decisions via AskUserQuestion: LICENSE = Apache-2.0, repo visibility = Public, execution = immediate batch 1 with per-task commit. HEAD = `46708e8`, tag `v1.0.2` (annotated) applied. 6 commits landed in order:
  1. `a1f2ad8` style: 修复预存 ruff lint 错误与格式漂移 — Pre-existing debt: 6 lint errors (`core/oversight_service.py` F401/I001, `frontend/app.py` I001, `scripts/live_e2e_four_stage.py` F541) + 8 format drift files. Fixed via `uv run ruff check --fix .` + `uv run ruff format .`.
  2. `14b2ea9` docs: 添加阶段 0 详细设计方案 — Created `docs/plan/phase-0-design.md` (404 lines): 现状复核 (5 findings, key = version metadata drift), T0.1–T0.8 task-level design with file drafts, Subagent parallel strategy + conflict analysis, risk table, acceptance checklist, 4 user decisions.
  3. `f49cb97` docs: 添加 SECURITY.md 与 CONTRIBUTING.md — T0.2 (SECURITY.md: GitHub Security Advisories 主渠道, supports v1.0.x, 7d response) + T0.3 (CONTRIBUTING.md: env setup → docs/local_setup.md, make lint/test/version-check 三步检查, Conventional Commits, PR 流程).
  4. `fe5ad78` ci: 最小化 CI 权限并启用 Dependabot — T0.4 (`.github/workflows/ci.yml`: inserted `permissions: contents: read` between `on:` and `concurrency:`) + T0.5 (`.github/dependabot.yml`: pip weekly / github-actions weekly, open-pull-requests-limit: 5).
  5. `8bffd74` docs: CHANGELOG 补充历史追溯说明 — T0.6: inserted 历史追溯说明 blockquote between `# Changelog` and `## v1.0 (2026-06-10)` explaining v0.1–v0.7 commit history retained on `origin`.
  6. `46708e8` chore: bump 版本至 1.0.2 并添加 Apache-2.0 LICENSE — T0.1 + T0.8: LICENSE file (Apache 2.0 full text from apache.org), version bump (`core/version.py` APP_VERSION/REPORT_SCHEMA_VERSION/PACKAGE_STAGE → 1.0.2; `pyproject.toml` → 1.0.2; `uv.lock` project version → 1.0.2; `README.md` 版本/协议行).连带修复 `tests/test_report_eval_regression_summary_v080_alpha2.py` 第 26 行断言 (1.0.0 → 1.0.2) 因 `core/eval_regression_policy.py:152` 使用 APP_VERSION.
- **Pre-batch 1 (2026-07-13, earlier same session)**: Design-plan authoring pass. New plan files (`phase-0-repo-governance.md` … `phase-4-community.md`), new spec files (4 specs), roadmap §10 复核增补, docs/README.md + CLAUDE.md index updates.

## Required Context Files

- `.upgrade/MANIFEST.md`
- `docs/plan/phase-0-design.md` — Phase 0 落地设计层（本批次实施依据）
- `docs/plan/phase-0-repo-governance.md` — Phase 0 实施计划（任务清单 + 验收标准）
- `docs/plan/improvement-roadmap.md` — roadmap; §10 supersedes conflicting body text
- `docs/plan/phase-1-security-compliance.md` … `phase-4-community.md` — 后续阶段
- `docs/spec/{supply-chain-security,data-classification-and-privacy,risk-taxonomy-engine,governance-platform}.md` — 设计状态规格

## Blockers

- Phase 0 T0.7 (Scorecard baseline) blocked on `scorecard` CLI 安装与 GitHub PAT 配置（如使用 Public 仓库 anonymous 模式则无鉴权阻塞，仅需安装 CLI）。
- Phase 3 T3.6 (LLM Judge) gated on user confirming real demand for automated evaluation (roadmap §8 preserved condition).

## Active Stage Report

Phase 0 Batch 1 verification (post-execution):
- `uv run python scripts/version_check.py` → `Version metadata OK: 1.0.2` ✅
- `uv run ruff check .` → `All checks passed!` ✅
- `uv run ruff format --check .` → `225 files already formatted` ✅
- `uv run pytest tests/ -q` → `397 passed, 1 skipped` ✅
- `git tag --list` → `v1.0.2` ✅
- HEAD = `46708e8` (chore: bump 版本至 1.0.2 并添加 Apache-2.0 LICENSE)

## Validation Commands

- `git status --short`
- `git diff`
- `uv run python scripts/version_check.py`
- `uv run ruff check . && uv run ruff format --check .`
- `Copy-Item -Force .env.demo .env; uv run pytest tests/ -q`
- `git tag --list` (expect `v1.0.2`)

## Next Action

Execute T0.7 OpenSSF Scorecard baseline scan:
1. Install `scorecard` CLI (local or via GitHub Action).
2. Run `scorecard --repo=github.com/gome09/ai-workflow-premortem-pure --format=json --show-details` (public repo anonymous mode acceptable per user decision).
3. Persist baseline report to `.upgrade/tmp/scorecard-baseline-<date>.json` per AGENTS.md.
4. Record findings to `.upgrade/decisions/scorecard-baseline.md` and update STATE.md.

After T0.7, Phase 0 is fully complete; ready to enter Phase 1 (security-compliance) per `docs/plan/phase-1-security-compliance.md`.

## Last Updated

- Date: 2026-07-13
- By: trae-agent (subagent-driven execution)
- Summary: Phase 0 Batch 1 executed (T0.1–T0.6, T0.8) — Apache-2.0 LICENSE, SECURITY.md, CONTRIBUTING.md, CI permission minimization, Dependabot, CHANGELOG traceability, version bump to 1.0.2 with v1.0.2 annotated tag. Pre-existing ruff lint/format debt cleared. All local validation green (version-check / ruff / pytest 397 pass). T0.7 Scorecard baseline remains.
