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

Populates the file-based `secrets/` directory used by `docker-compose.yml`, and keeps `.env` in
sync where the application's config precedence requires it. Invoked by `make setup`.
Run once per environment setup. Not part of CI.

```bash
bash scripts/gen_secrets.sh
```

What it does, precisely:

1. Generates four random service values plus two independent Fernet-compatible values
   (`data_encryption_key`, `checkpoint_encryption_key`) into `secrets/` — each `chmod 600`.
2. Syncs **three** of them (`JWT_SECRET`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD`) back into the
   matching `CHANGE_ME` lines in `.env`. This is required because `.env` values shadow
   `/run/secrets` in the settings precedence order. `grafana_password` is *not* synced — Grafana
   reads it directly via `GF_SECURITY_ADMIN_PASSWORD__FILE`.
3. Comments out the `CHANGE_ME` placeholder lines for `DEEPSEEK_API_KEY` / `TAVILY_API_KEY`,
   which cannot be generated and must be filled in manually when `LLM_MODE=real`.

Docker Full reads the two encryption values from file secrets. Non-Docker deployments can instead
set the matching environment variables; they have higher precedence. The values must remain
different — see `.env.example` and `docs/startup.md`.

### live_e2e_four_stage.py

Drives the full Stage 1–4 workflow against a **already-running** backend over the authenticated
API, using the `generic_rag_demo` mock scenario. Used for manual acceptance runs; not a CI step
and not wired to any Makefile target.

```bash
# backend must already be listening on 127.0.0.1:8000 (e.g. `make demo-api`)
uv run python scripts/live_e2e_four_stage.py
```

`BASE_URL` is hardcoded to `http://127.0.0.1:8000` — there is no CLI flag or environment
override. Edit the constant if you need a different host or port.

## Archive

`scripts/archive/` contains scripts that are **not** part of the current production workflow:

| Script | Reason archived |
|---|---|
| `migrate_add_tenant_once.py` | One-time tenant backfill migration, already applied |

Archived scripts are not invoked by CI, Makefile, or Docker builds.
See `scripts/archive/README.md` for the retained migration's safety boundary and the cleanup record.
