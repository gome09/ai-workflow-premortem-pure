"""Contract placeholders for v0.7.0-alpha.4 StageAdvancementDecision.

These tests are intentionally added for the later unified validation pass. They
are not executed as part of the source-level patch generation.
"""

from core.models import ProjectContext
from core.stage_advancement_coordinator import build_stage_advancement_decision


def test_stage_advancement_decision_blocks_missing_output():
    ctx = ProjectContext()
    decision = build_stage_advancement_decision(ctx, 1)
    assert decision.can_advance is False
    assert decision.advanced is False
    assert decision.gate_result.blockers
    assert decision.required_operations


def test_stage_advancement_decision_is_read_only():
    ctx = ProjectContext()
    before_state = ctx.current_state
    build_stage_advancement_decision(ctx, 1)
    assert ctx.current_state == before_state
