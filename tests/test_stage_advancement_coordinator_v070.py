"""Contract placeholders for v0.7.0-alpha.4 stage advancement coordinator.

These tests are intended for the later unified validation pass and are not run
during this patch.
"""

from core.models import ProjectContext
from core.stage_advancement_coordinator import advance_stage_if_ready


def test_advance_stage_if_ready_does_not_advance_when_gate_blocked():
    ctx = ProjectContext()
    decision = advance_stage_if_ready(ctx, 1, reason="test")
    assert decision.can_advance is False
    assert decision.advanced is False
    assert ctx.current_state.value == "init"
