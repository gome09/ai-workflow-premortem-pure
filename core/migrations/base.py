# core/migrations/base.py
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

RawContext = dict[str, Any]
MigrationFn = Callable[[RawContext], RawContext]


@dataclass(frozen=True)
class ContextMigration:
    from_version: str
    to_version: str
    name: str
    fn: MigrationFn
