# Storage Layer

## Migration Mechanism

The current database schema migration mechanism is **Alembic**.

### Production startup path

1. `api/main.py` initializes the session store in the `lifespan` context manager.
2. `storage/backends/postgres.py::PostgresSessionStore.initialize()` runs `alembic upgrade head`.
3. Alembic migrations are under `alembic/versions/` (V001 → V003 at v1.0).

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

## Note on removed code

The `storage/migrations/` package that previously contained hand-written SQL migrations
(`run_storage_migrations()`) was removed in v1.0. Those SQL statements overlapped with Alembic
migrations and were never called by any application code.
