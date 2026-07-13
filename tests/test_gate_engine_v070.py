"""v0.7 GateEngine contract tests for the later unified validation pass."""

from __future__ import annotations

from core.gates.engine import evaluate_stage_gate
from core.models import ProjectContext


def test_gate_engine_returns_rule_ids_on_blockers():
    ctx = ProjectContext()
    result = evaluate_stage_gate(ctx, 1)

    assert result.stage_id == 1
    for blocker in result.blockers:
        assert blocker.rule_id
