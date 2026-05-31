# Stage Advancement Source Freeze Audit — alpha.11

Generated: 2026-05-29  
Package stage: `v0.8.0-alpha.11-freeze-fix`  
Runtime validation: `deferred_by_instruction`

## Purpose

This document defines the static checks that should be run before accepting alpha.11 and moving into `v0.9.0-pre-alpha.1-governance-scaffolding`.

## Script

```text
scripts/static/stage_advancement_source_freeze_audit.py
```

The script is intentionally source-only. It should not start FastAPI, Streamlit, Docker, PostgreSQL, Redis, LLM, Search, or pytest.

## Checks covered

1. `BLOCKER_TYPES` must match `STAGE_ADVANCEMENT_CONTRACT` keys.
2. Every contract `required_resolution` must exist in `REQUIRED_RESOLUTIONS`.
3. Every `REQUIRED_RESOLUTION` must exist in `RESOLUTION_OPERATION_CONTRACT`.
4. Gate rule files must not emit unknown `blocker_type` or `required_resolution` strings.
5. Active metadata must identify the package as alpha.11 freeze-fix.
6. Eval Regression policy must source `policy_version` from `APP_VERSION`.
7. Alpha.11 API audit must mark EvalDataset mutating endpoints as gate-affecting.
8. Runtime validation must remain `deferred_by_instruction`.

## Not covered

This audit does not prove runtime correctness. Unified validation remains required later.
