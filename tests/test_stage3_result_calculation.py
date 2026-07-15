# tests/test_stage3_result_calculation.py
"""WS-7: Deterministic Stage 3 overall_passed calculator.

Validates ``compute_overall_passed`` which overrides fixture-hardcoded
``overall_passed`` values based on ``final_pass_status`` and
``human_review_result`` of each ``StressTestResult``.
"""

from __future__ import annotations

from core.models import (
    FailureMode,
    ProjectContext,
    Stage1Output,
    Stage3Output,
    StressTestResult,
)
from core.stage3_result_calculator import (
    apply_deterministic_overall_passed,
    compute_overall_passed,
)


def _ctx_with(
    *,
    failure_modes: list[FailureMode] | None = None,
    test_results: list[StressTestResult] | None = None,
    stage_3_output: Stage3Output | None = None,
) -> ProjectContext:
    ctx = ProjectContext()
    ctx.session_id = "sess-stage3-calc"
    ctx.tenant_id = "tenant-stage3"
    if failure_modes is not None:
        ctx.stage_1_output = Stage1Output(failure_modes=failure_modes)
    if stage_3_output is not None:
        ctx.stage_3_output = stage_3_output
    elif test_results is not None:
        ctx.stage_3_output = Stage3Output(test_results=test_results)
    return ctx


def _fm(fm_id: str, severity: str = "medium") -> FailureMode:
    return FailureMode(id=fm_id, category="...", description="...", severity=severity)


def _result(
    *,
    fm_id: str = "",
    node_id: str = "NODE-1",
    case_id: str = "TC-1",
    final_pass_status: str = "passed",
    human_review_result: str = "not_required",
) -> StressTestResult:
    return StressTestResult(
        tested_node_id=node_id,
        test_input="...",
        ai_output="...",
        case_id=case_id,
        failure_mode_id=fm_id,
        final_pass_status=final_pass_status,  # type: ignore[arg-type]
        human_review_result=human_review_result,  # type: ignore[arg-type]
    )


# ─────────────────────────────────────────────
# No output / no results → False
# ─────────────────────────────────────────────


def test_no_stage3_output_returns_false():
    ctx = ProjectContext()
    assert compute_overall_passed(ctx) is False


def test_no_test_results_returns_false():
    ctx = _ctx_with(stage_3_output=Stage3Output(test_results=[]))
    assert compute_overall_passed(ctx) is False


# ─────────────────────────────────────────────
# All passed and reviewed → True
# ─────────────────────────────────────────────


def test_all_passed_with_review_returns_true():
    ctx = _ctx_with(
        failure_modes=[_fm("FM-A", "high"), _fm("FM-B", "medium")],
        test_results=[
            _result(
                fm_id="FM-A",
                final_pass_status="passed",
                human_review_result="approved",
            ),
            _result(
                fm_id="FM-B",
                final_pass_status="passed",
                human_review_result="not_required",
            ),
        ],
    )
    assert compute_overall_passed(ctx) is True


def test_low_risk_fm_passed_without_review_returns_true():
    """Low/medium FMs do not require human_review_result to be non-pending."""
    ctx = _ctx_with(
        failure_modes=[_fm("FM-LOW", "low"), _fm("FM-MED", "medium")],
        test_results=[
            _result(
                fm_id="FM-LOW",
                final_pass_status="passed",
                human_review_result="pending",  # low-risk, pending review is OK
            ),
            _result(
                fm_id="FM-MED",
                final_pass_status="passed",
                human_review_result="pending",
            ),
        ],
    )
    assert compute_overall_passed(ctx) is True


# ─────────────────────────────────────────────
# Any failed/pending/blocked → False
# ─────────────────────────────────────────────


def test_any_failed_returns_false():
    ctx = _ctx_with(
        test_results=[
            _result(case_id="TC-1", final_pass_status="passed"),
            _result(case_id="TC-2", final_pass_status="failed"),
        ],
    )
    assert compute_overall_passed(ctx) is False


def test_any_pending_returns_false():
    ctx = _ctx_with(
        test_results=[
            _result(case_id="TC-1", final_pass_status="passed"),
            _result(case_id="TC-2", final_pass_status="pending"),
        ],
    )
    assert compute_overall_passed(ctx) is False


def test_any_blocked_returns_false():
    ctx = _ctx_with(
        test_results=[
            _result(case_id="TC-1", final_pass_status="passed"),
            _result(case_id="TC-2", final_pass_status="blocked"),
        ],
    )
    assert compute_overall_passed(ctx) is False


# ─────────────────────────────────────────────
# High/critical FM with pending human review → False
# ─────────────────────────────────────────────


def test_high_risk_fm_pending_review_returns_false():
    ctx = _ctx_with(
        failure_modes=[_fm("FM-HIGH", "high")],
        test_results=[
            _result(
                fm_id="FM-HIGH",
                final_pass_status="passed",
                human_review_result="pending",  # high-risk, pending → False
            ),
        ],
    )
    assert compute_overall_passed(ctx) is False


def test_critical_risk_fm_pending_review_returns_false():
    ctx = _ctx_with(
        failure_modes=[_fm("FM-CRIT", "critical")],
        test_results=[
            _result(
                fm_id="FM-CRIT",
                final_pass_status="passed",
                human_review_result="pending",
            ),
        ],
    )
    assert compute_overall_passed(ctx) is False


def test_high_risk_fm_approved_review_returns_true():
    ctx = _ctx_with(
        failure_modes=[_fm("FM-HIGH", "high")],
        test_results=[
            _result(
                fm_id="FM-HIGH",
                final_pass_status="passed",
                human_review_result="approved",
            ),
        ],
    )
    assert compute_overall_passed(ctx) is True


def test_high_risk_fm_rejected_review_returns_true():
    """rejected is not 'pending' — the calculator only blocks on pending review."""
    ctx = _ctx_with(
        failure_modes=[_fm("FM-HIGH", "high")],
        test_results=[
            _result(
                fm_id="FM-HIGH",
                final_pass_status="passed",
                human_review_result="rejected",
            ),
        ],
    )
    assert compute_overall_passed(ctx) is True


# ─────────────────────────────────────────────
# apply_deterministic_overall_passed mutates ctx
# ─────────────────────────────────────────────


def test_apply_deterministic_overall_passed_writes_field():
    ctx = _ctx_with(
        test_results=[
            _result(case_id="TC-1", final_pass_status="failed"),
        ],
    )
    # Force a True value to confirm the helper overwrites it
    assert ctx.stage_3_output is not None
    ctx.stage_3_output.overall_passed = True
    result = apply_deterministic_overall_passed(ctx)
    assert result is False
    assert ctx.stage_3_output.overall_passed is False


def test_apply_deterministic_overall_passed_no_output_returns_false():
    ctx = ProjectContext()
    assert apply_deterministic_overall_passed(ctx) is False
