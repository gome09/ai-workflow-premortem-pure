"""v0.7 reviewed output atomicity tests for later unified validation."""

from __future__ import annotations

from copy import deepcopy

from core.models import ProjectContext
from core.reviewed_output_service import apply_reviewed_output_with_result


def test_invalid_reviewed_output_does_not_mutate_existing_reviewed_payload():
    ctx = ProjectContext()
    before = deepcopy(ctx.reviewed_outputs)

    try:
        apply_reviewed_output_with_result(ctx, 1, {"failure_modes": "not-a-list"})
    except Exception:
        pass

    assert ctx.reviewed_outputs == before
