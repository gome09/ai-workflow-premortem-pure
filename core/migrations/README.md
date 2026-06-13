# Legacy Context Migrations

These migrations are retained for backward compatibility with persisted context JSON
records that predate the v1.0 schema.

They are **not** a general-purpose schema migration mechanism — database schema
migrations are managed by Alembic (see `alembic/versions/`).

## Why this is still active in v1.0

`storage/backends/postgres.py` and `storage/backends/sqlite_store.py` call
`migrate_context()` on every context load. This ensures that any context JSON
written before v0.7.0 is automatically upgraded to the current schema at read time.

The current context schema version is `"0.7.0"`, defined in:
- `core/migrations/registry.py` → `CURRENT_CONTEXT_SCHEMA_VERSION`
- `core/models.py` → `CONTEXT_SCHEMA_VERSION`

## Safe to remove when

All persisted context records have been confirmed to have `context_schema_version >= "0.7.0"`.
At that point, the `migrate_context()` call in the storage backends becomes a no-op and
the entire `core/migrations/` package can be removed.

## Migration chain

`"0.6.0-alpha.8"` → `"0.7.0"` via `v060_alpha8_to_v070.py`
