# core/migrations/registry.py
from __future__ import annotations

from copy import deepcopy
from typing import Any

from core.migrations.base import ContextMigration, MigrationFn
from core.models import ProjectContext

CURRENT_CONTEXT_SCHEMA_VERSION = "0.10.0"
LEGACY_CONTEXT_SCHEMA_VERSION = "0.6.0-alpha.8"

_MIGRATIONS: list[ContextMigration] = []


def register_migration(from_version: str, to_version: str, fn: MigrationFn) -> None:
    name = getattr(fn, "__name__", f"{from_version}_to_{to_version}")
    existing = [
        m for m in _MIGRATIONS if m.from_version == from_version and m.to_version == to_version
    ]
    if existing:
        return
    _MIGRATIONS.append(ContextMigration(from_version, to_version, name, fn))


def _find_migration(from_version: str) -> ContextMigration | None:
    for migration in _MIGRATIONS:
        if migration.from_version == from_version:
            return migration
    return None


def migrate_context(raw: dict[str, Any] | ProjectContext) -> ProjectContext:
    """Load context_json through the v0.7 migration boundary.

    The migration never mutates the caller's raw object.  Unknown future schemas
    are validated as-is so newer exports can still be inspected manually.
    """
    if isinstance(raw, ProjectContext):
        return raw

    current: dict[str, Any] = deepcopy(raw or {})
    version = current.get("context_schema_version") or LEGACY_CONTEXT_SCHEMA_VERSION

    if version == CURRENT_CONTEXT_SCHEMA_VERSION:
        return ProjectContext.model_validate(current)

    guard = 0
    while version != CURRENT_CONTEXT_SCHEMA_VERSION:
        guard += 1
        if guard > 10:
            raise ValueError("ProjectContext migration chain exceeded safety limit")
        migration = _find_migration(str(version))
        if migration is None:
            warnings = list(current.get("migration_warnings") or [])
            warnings.append(
                f"No registered migration from {version}; validating with ProjectContext defaults."
            )
            current["migration_warnings"] = warnings
            break
        current = migration.fn(current)
        version = current.get("context_schema_version") or migration.to_version

    current.setdefault("context_schema_version", CURRENT_CONTEXT_SCHEMA_VERSION)
    return ProjectContext.model_validate(current)
