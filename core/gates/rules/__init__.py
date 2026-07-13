# core/gates/rules/__init__.py
from __future__ import annotations

from core.gates.base import GateRule
from core.gates.rules import (
    action_state,
    eval_regression,
    missing_output,
    parser_error,
    redteam_coverage,
    safety_finding,
    stage1_evidence_gap,
    stage2_policy_gap,
    stage3_eval_failure,
    stage4_final_governance,
    stale_dependency,
    trace_backfill_gap,
)


def registered_rules() -> list[GateRule]:
    return [
        missing_output.rule,
        stale_dependency.rule,
        action_state.rule,
        parser_error.rule,
        safety_finding.rule,
        stage1_evidence_gap.rule,
        stage2_policy_gap.rule,
        stage3_eval_failure.rule,
        redteam_coverage.rule,
        eval_regression.rule,
        trace_backfill_gap.rule,
        stage4_final_governance.rule,
    ]
