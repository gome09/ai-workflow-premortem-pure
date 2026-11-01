# Document, GitHub CI/CD and `.upgrade` Alignment (2026-11-01)

## Decisions

1. **Version authority**: this round aligns on `1.7.0` (already in `core/version.py`, `pyproject.toml`, `uv.lock`, `CHANGELOG.md`); no new release version.
2. **Fact priority**: code / migrations / tests > version metadata > `docs/spec` and startup guides > `.upgrade/STATE.md` > archive. Historical archive content is not rewritten; only "current" claims are corrected.
3. **Commit split**: commit 1 = v1.7.0 code + tests + CI/version metadata (including dynamic Alembic head and `core/coverage` tracking, already in `7966f9d`); commit 2 = documentation + `.upgrade` synchronization; commit 3 = append-only verification backfill of run IDs/results. All three are pushed and each waits for GitHub Actions.
4. **Dependency audit policy**: GitHub Actions keeps `make lint` blocking and runs `make audit` as an independent `continue-on-error` observation step; local `make security-check` stays strict. Reason: the external advisory database grew to 124 unique advisories / 19 packages on 2026-11-01. `pillow` cannot be upgraded while streamlit pins `pillow<13`, `ecdsa` has no fix, and `langgraph-checkpoint-postgres` is intentionally fixed at `3.0.5` by the V006 schema guard. User approved this decision on 2026-11-01.
5. **Acceptance report**: `docs/acceptance_report.md` remains the "current" report; the v1.3.0 baseline section is retained and explicitly labelled as history instead of creating a new file.
6. **No checker-rule expansion**: `scripts/version_check.py` continues to compare only `core/version.py` and `pyproject.toml`; README/doc version assertions are not added in this round.
7. **Validation records**: `.upgrade/validation/records.jsonl` is not hand-appended because the `subject_digest` generation semantics cannot be reproduced locally without the maintainer CLI. Actual results are recorded in `.upgrade/STATE.md` (`last_validation`) and an append-only trace; fabricating governance evidence is prohibited.
8. **Remote scope**: branch protection, private vulnerability reporting, CodeQL required check and GitHub Release remain `unverified` until a maintainer verifies them in the GitHub settings; local files cannot prove remote state.

## Verification Notes

- Local (2026-11-01, project `.venv`, `sqlite` + `memory` + `mock`): `ruff check` clean; `ruff format --check` 392 files; mypy 199 files 0 issues; doc-check 37 Markdown files 0 violations; version-check `1.7.0`; pytest `1131 passed, 4 skipped` (72.73s).
- Local `make audit` failed with 124 unique advisories / 19 packages; treated as a non-blocking observation in CI per decision 4 and recorded in `.upgrade/STATE.md` Blockers.
- GNU `make` is unavailable in the current Windows shell; the underlying commands were executed directly.
- Docker daemon / Redis were not available locally; Docker and PostgreSQL/Redis E2E evidence is delegated to CI `docker-*` and `production-safety` jobs.
