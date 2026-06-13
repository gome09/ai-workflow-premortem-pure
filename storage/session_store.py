# storage/session_store.py
"""
Factory wrapper — selects the correct backend based on STORAGE_BACKEND env var.

Callers continue to use:
    from storage.session_store import session_store

The public interface of `session_store` is unchanged regardless of backend.

Backward-compat alias:
    from storage.session_store import SessionStore   # returns PostgresSessionStore class
"""

from __future__ import annotations

from core.config import settings


def _make_store():
    if settings.storage_backend == "sqlite":
        from storage.backends.sqlite_store import SQLiteSessionStore

        return SQLiteSessionStore()
    from storage.backends.postgres import PostgresSessionStore

    return PostgresSessionStore()


# Global singleton — identical public API regardless of backend
session_store = _make_store()

# Backward-compatibility alias so any code that did
#   from storage.session_store import SessionStore
# still resolves to the active backend class.
SessionStore = type(session_store)
