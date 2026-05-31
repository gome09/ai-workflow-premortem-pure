# storage/migrations/__init__.py
from storage.migrations.registry import run_storage_migrations

__all__ = ["run_storage_migrations"]
