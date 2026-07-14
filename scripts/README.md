# Scripts

This directory contains utility scripts for the ai-workflow project.

## Active Scripts

### version_check.py

Validates that `pyproject.toml` and `core/version.py` declare the same `APP_VERSION`.
Run as part of the pre-release checklist:

```bash
python scripts/version_check.py
# or via Makefile:
make version-check
```

Safe for CI. No external dependencies beyond the project itself.

### doc_consistency_check.py

Validates documentation-code consistency: checks that relative Markdown links resolve, `make <target>` references exist in Makefile, and backtick-quoted repo paths exist.

```bash
python scripts/doc_consistency_check.py
# or via Makefile:
make doc-check
```

Three rule classes (see `docs/spec/supply-chain-security.md` §7):
1. Link existence (relative paths in README.md / CLAUDE.md / docs/**/*.md)
2. Make target existence
3. Backtick repo path existence (heuristic: must start with a known top-level dir)

Non-blocking in CI initially (`continue-on-error: true`); promoted to blocking after存量坏链 cleared.

### gen_certs.sh / gen_certs.ps1

Generates self-signed TLS certificates for local HTTPS development.
Run once per environment setup. Not part of CI.

```bash
bash scripts/gen_certs.sh
```

### gen_secrets.sh

Generates random secret values for `.env` files (JWT secret, passwords, etc.).
Run once per environment setup. Not part of CI.

```bash
bash scripts/gen_secrets.sh
```

## Archive

`scripts/archive/` contains scripts that are **not** part of the current v1.0 release:

| Script | Reason archived |
|---|---|
| `stage_advancement_source_freeze_audit_alpha11.py` | Validates alpha.11 assumptions, stale for v1.0 |
| `migrate_add_tenant_once.py` | One-time tenant backfill migration, already applied |
| `live_e2e_low_risk_room_booking.py` | Manual live E2E, not in CI |
| `live_e2e_student_management_v2.py` | Manual live E2E, not in CI |

Archived scripts are not invoked by CI, Makefile, or Docker builds.
See `scripts/archive/README.md` for per-script details.
