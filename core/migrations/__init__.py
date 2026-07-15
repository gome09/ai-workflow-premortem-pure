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
from core.migrations.v080_to_v090 import migrate_v080_to_v090
from core.migrations.v090_to_v0100 import migrate_v090_to_v0100

register_migration(
    LEGACY_CONTEXT_SCHEMA_VERSION,
    "0.7.0",
    migrate_v060_alpha8_to_v070,
)

register_migration(
    "0.7.0",
    "0.8.0",
    migrate_v070_to_v080,
)

register_migration(
    "0.8.0",
    CURRENT_CONTEXT_SCHEMA_VERSION,
    migrate_v080_to_v090,
)

register_migration(
    "0.9.0",
    CURRENT_CONTEXT_SCHEMA_VERSION,
    migrate_v090_to_v0100,
)

__all__ = [
    "CURRENT_CONTEXT_SCHEMA_VERSION",
    "LEGACY_CONTEXT_SCHEMA_VERSION",
    "migrate_context",
    "register_migration",
]
