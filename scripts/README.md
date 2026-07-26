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
1. Link existence across current project Markdown (excluding `.upgrade/`, archive trees, runtime artifacts, and tool caches)
2. Make target existence
3. Backtick repo path existence (heuristic: must start with a known top-level dir)

This check is blocking in CI. The earlier observation-period `continue-on-error` setting has been removed.

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

`scripts/archive/` contains scripts that are **not** part of the current production workflow:

| Script | Reason archived |
|---|---|
| `migrate_add_tenant_once.py` | One-time tenant backfill migration, already applied |

Archived scripts are not invoked by CI, Makefile, or Docker builds.
See `scripts/archive/README.md` for the retained migration's safety boundary and the cleanup record.
