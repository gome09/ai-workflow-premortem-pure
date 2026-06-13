from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from core.models import ProjectContext


class GateRule(Protocol):
    """Gate rule contract.

    Rules evaluate one stage and return zero or more StageBlocker-like objects.
    The concrete StageBlocker model remains in `core.stage_readiness_service`
    for backward compatibility with existing API/frontend contracts.
    """

    rule_id: str
    applies_to_stages: set[int]

    def applies_to(self, stage: int) -> bool: ...

    def evaluate(self, ctx: ProjectContext, stage: int) -> list[Any]: ...


@dataclass(frozen=True)
class CollectorGateRule:
    """Compatibility adapter for legacy blocker collectors."""

    rule_id: str
    applies_to_stages: set[int]
    collect: Callable[[ProjectContext, int], list[Any]]

    def applies_to(self, stage: int) -> bool:
        return stage in self.applies_to_stages

    def evaluate(self, ctx: ProjectContext, stage: int) -> list[Any]:
        blockers = self.collect(ctx, stage)
        for blocker in blockers:
            if not getattr(blocker, "rule_id", ""):
                blocker.rule_id = self.rule_id
        return blockers
