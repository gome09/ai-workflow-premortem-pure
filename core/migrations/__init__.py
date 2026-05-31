# core/migrations/__init__.py
from __future__ import annotations

from core.migrations.registry import (
    CURRENT_CONTEXT_SCHEMA_VERSION,
    LEGACY_CONTEXT_SCHEMA_VERSION,
    migrate_context,
    register_migration,
)
from core.migrations.v060_alpha8_to_v070 import migrate_v060_alpha8_to_v070

register_migration(
    LEGACY_CONTEXT_SCHEMA_VERSION,
    CURRENT_CONTEXT_SCHEMA_VERSION,
    migrate_v060_alpha8_to_v070,
)

__all__ = [
    "CURRENT_CONTEXT_SCHEMA_VERSION",
    "LEGACY_CONTEXT_SCHEMA_VERSION",
    "migrate_context",
    "register_migration",
]
