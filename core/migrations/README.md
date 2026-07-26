# Legacy Context Migrations

These migrations are retained for backward compatibility with persisted context JSON
records that predate the v1.0 schema.

They are **not** a general-purpose schema migration mechanism — database schema
migrations are managed by Alembic (see `alembic/versions/`).

## Why this is still active

`storage/backends/postgres.py` and `storage/backends/sqlite_store.py` call
`migrate_context()` on every context load. This ensures that any context JSON
using any registered older schema (`0.6.0-alpha.8`, `0.7.0`, or `0.8.0`) is
automatically upgraded to the current schema at read time.

The current context schema version is `"0.9.0"`, defined in:
- `core/migrations/registry.py` → `CURRENT_CONTEXT_SCHEMA_VERSION`
- `core/models.py` → `CONTEXT_SCHEMA_VERSION`

## Safe to remove when

All persisted context records have been confirmed to match
`CURRENT_CONTEXT_SCHEMA_VERSION` (currently `"0.9.0"`), and both storage backends no
longer call `migrate_context()`. Checking only for `>= "0.7.0"` is insufficient because
the `0.7.0 → 0.8.0 → 0.9.0` steps are still active. Only after those conditions hold can
the entire `core/migrations/` package be considered for removal.

## Migration chain

`"0.6.0-alpha.8"` → `"0.7.0"` via `v060_alpha8_to_v070.py`

`"0.7.0"` → `"0.8.0"` via `v070_to_v080.py`

`"0.8.0"` → `"0.9.0"` via `v080_to_v090.py`
