# core/gates/rules/__init__.py
from __future__ import annotations

import logging

from core.gates.base import GateRule
from core.gates.rules import (
    action_state,
    eval_regression,
    expert_review,
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
from core.gates.rules.manifest import RULE_MANIFEST

logger = logging.getLogger(__name__)


def registered_rules() -> list[GateRule]:
    rules: list[GateRule] = [
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
        expert_review.rule,
    ]
    _verify_manifest_integrity(rules)
    return rules


def _verify_manifest_integrity(rules: list[GateRule]) -> None:
    """启动时校验：每条注册规则有 manifest 条目，每个 manifest 条目有实现。

    双向完整性失败只记 WARNING 不抛异常——避免新增 manifest 条目但实现未上线时
    阻断启动（前向兼容）。完整性由测试固化。
    """
    implemented_ids = {r.rule_id for r in rules}
    manifest_ids = set(RULE_MANIFEST.keys())
    missing_manifest = implemented_ids - manifest_ids
    missing_impl = manifest_ids - implemented_ids
    if missing_manifest:
        logger.warning("Rules without manifest entry: %s", sorted(missing_manifest))
    if missing_impl:
        logger.warning("Manifest entries without implementation: %s", sorted(missing_impl))
