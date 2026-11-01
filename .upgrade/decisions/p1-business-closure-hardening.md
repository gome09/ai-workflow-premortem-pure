# P1 Business Closure Hardening (2026-11-01, v1.7.0)

## Decisions

1. **Single workspace membership**: `users.tenant_id` remains single-valued. Registration creates a workspace and the creator is always admin. Additional members join only through `workspace_invitations`; multi-workspace switching is out of scope.
2. **Invitation delivery**: raw invitation tokens are returned once to the inviting admin; the database stores only SHA-256 hashes. No email delivery is implemented.
3. **Refresh semantics**: `/auth/refresh` re-reads the current user record and issues the current role. Existing access tokens keep their claim until the normal 15-minute expiry; no token-version table was introduced.
4. **Evaluation version schema 2.0**: includes materials, target deployment, monotonic input versions, EvalCase definitions/`standard_version` and policy versions. Runs, treatments, approvals, calibrations and audit data are excluded to avoid a circular dependency.
5. **Strict release batch**: release evidence must come from one completed `target_http` EvalExperiment covering every required high-risk EvalCase. A run counts only when `execution_outcome=success`, `judge_result=passed`, and evaluation/case/deployment bindings still match current state.
6. **Approval invalidation is permanent**: `ProjectApproval.evidence_digest` snapshots treatments, calibrations, safety findings and blocking actions. Any later negative change yields `effective_status=invalidated`; history is retained but the old approval never revives, even after conditions recover.
7. **One-time evidence reset**: schema 2.0 and stricter binding intentionally invalidate pre-1.7 approvals, treatments and EvalRuns. Operators must re-submit treatments, re-run target tests and re-approve after upgrade.
8. **`goal` backfill**: existing plaintext `goal` remains readable after the code fix; `scripts/encrypt_legacy_goal.py` performs idempotent backfill (dry-run default) and provides verify/decrypt modes for rollback.
9. **Alembic shadowing fix**: `alembic/__init__.py` was removed because it shadowed the installed `alembic` package and broke `from alembic.config import Config`. The migrations directory is data, not a Python package.
10. **ProjectContext schema stays 0.10.0**: new fields (`target_deployment`, `input_versions`, `EvalCase.standard_version`, `EvalRun` bindings, `ProjectApproval.evidence_digest`) are optional defaults; no context migration is required.

## Verification Notes

- Offline: `1131 passed, 4 skipped` (SQLite + memory + mock).
- Real PostgreSQL 18 temporary trust cluster: V008→V012 upgrade/rollback/re-upgrade (2 passed); goal ciphertext/backfill/invitation/refresh (3 passed).
- Redis/Docker were not used per user instruction; PostgreSQL + Redis workflow E2E remains delegated to CI `production-safety` with `PRODUCTION_SAFETY_REQUIRED=1`.
- Ruff, `ruff format --check`, mypy, doc-check, version-check all passed.
