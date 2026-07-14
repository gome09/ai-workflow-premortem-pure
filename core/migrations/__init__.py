# core/migrations/__init__.py
from __future__ import annotations

from core.migrations.registry import (
    CURRENT_CONTEXT_SCHEMA_VERSION,
    LEGACY_CONTEXT_SCHEMA_VERSION,
    migrate_context,
    register_migration,
)
from core.migrations.v060_alpha8_to_v070 import migrate_v060_alpha8_to_v070
from core.migrations.v070_to_v080 import migrate_v070_to_v080

register_migration(
    LEGACY_CONTEXT_SCHEMA_VERSION,
    "0.7.0",
    migrate_v060_alpha8_to_v070,
)

register_migration(
    "0.7.0",
    CURRENT_CONTEXT_SCHEMA_VERSION,
    migrate_v070_to_v080,
)

__all__ = [
    "CURRENT_CONTEXT_SCHEMA_VERSION",
    "LEGACY_CONTEXT_SCHEMA_VERSION",
    "migrate_context",
    "register_migration",
]
