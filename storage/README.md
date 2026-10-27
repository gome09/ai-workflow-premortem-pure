# Storage Layer

## Migration Mechanism

The current database schema migration mechanism is **Alembic**.

### Production startup path

1. `api/main.py` initializes the session store in the `lifespan` context manager.
2. `storage/backends/postgres.py::PostgresSessionStore.initialize()` runs `alembic upgrade head`.
3. Alembic migrations are under `alembic/versions/` (currently V001 → V008).
   V006 adds the LangGraph PostgreSQL checkpoint schema; V007 adds the durable
   interrupt-resume outbox; V008 adds `sessions.version` (optimistic locking),
   JSONB generated columns, tenant indexes and `human_actions.tenant_id`.
   Runtime code validates these tables but does not create or upgrade them ad hoc.

### Legacy databases created before Alembic

A database created by hand before this migration chain has no `alembic_version`
table and may lack columns that V001 assumes (for example `sessions.tenant_id`).
Running `alembic upgrade head` directly fails: `CREATE TABLE IF NOT EXISTS` keeps
the existing tables unchanged, but the tenant indexes created immediately after
them reference missing columns.

Upgrade such a database in four steps:

1. Back up with `pg_dump` and store the dump outside the repository tree
   (`.upgrade/backup/` is git-ignored).
2. Diff it against a database that has run V001 → V008, then
   `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` every missing non-generated column.
3. Insert the baseline row into `alembic_version` (or run `alembic stamp V001`)
   so the chain does not try to recreate existing tables.
4. Run `alembic upgrade head` and verify the V008 columns, indexes and constraints.

Rows predating the multi-tenant model keep `tenant_id = NULL`; backfill them to a
real tenant before relying on tenant-scoped reads or governance aggregates.

### SQLite (lite mode)

`storage/backends/sqlite_store.py::SQLiteSessionStore.initialize()` creates all tables inline
via DDL — no Alembic needed.

## Backends

| Module | Backend | Activation |
|--------|---------|------------|
| `storage/backends/postgres.py` | PostgreSQL | `STORAGE_BACKEND=postgres` (default) |
| `storage/backends/sqlite_store.py` | SQLite | `STORAGE_BACKEND=sqlite` |

## Cache

| Module | Backend | Activation |
|--------|---------|------------|
| `storage/cache.py` → `ContextCache` | Redis | Postgres mode |
| `storage/cache.py` → `MemoryCache` (from `storage/backends/memory_cache.py`) | In-process dict | SQLite / lite mode |
