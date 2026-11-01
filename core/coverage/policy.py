# core/coverage/policy.py
"""Single source of truth for high-risk workflow nodes and Stage 3 sampling.

All functions are deterministic and read-only over ``ProjectContext``. HIGH and
CRITICAL projects must select every high-risk node regardless of budget; only
LOW/MEDIUM (and the non-mandatory tail of HIGH) use budgeted sampling.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from core.config import settings
from core.models import ProjectContext, WorkflowNode
from core.risk.assessment import assess_project_risk
from core.risk.models import ProjectGateRiskTier

_SEVERITY_WEIGHT = {"critical": 4, "high": 3, "medium": 1, "low": 0}

# Bump when the coverage selection / minimum-case policy changes; included in
# the evaluation-version policy snapshot.
COVERAGE_POLICY_VERSION = "1.0"


@dataclass(frozen=True)
class CoveragePolicy:
    risk_tier: ProjectGateRiskTier
    required_node_ids: list[str]
    selected_node_ids: list[str]
    sample_budget: int
    min_coverage_ratio: float
    min_cases_per_high_risk_node: int
    rationale: str

    def as_dict(self) -> dict:
        return {
            "risk_tier": self.risk_tier.value,
            "required_node_ids": list(self.required_node_ids),
            "selected_node_ids": list(self.selected_node_ids),
            "sample_budget": self.sample_budget,
            "min_coverage_ratio": self.min_coverage_ratio,
            "min_cases_per_high_risk_node": self.min_cases_per_high_risk_node,
            "rationale": self.rationale,
        }


def high_risk_failure_mode_ids(
    ctx: ProjectContext, tier: ProjectGateRiskTier | None = None
) -> set[str]:
    """Return failure mode ids that require high-risk node coverage for *tier*."""
    if not ctx.stage_1_output:
        return set()
    resolved = tier or assess_project_risk(ctx).effective_tier
    severity_filter = {"critical"} if resolved == ProjectGateRiskTier.LOW else {"high", "critical"}
    return {
        failure_mode.id
        for failure_mode in ctx.stage_1_output.failure_modes
        if str(failure_mode.severity).lower() in severity_filter
    }


def _nodes(ctx: ProjectContext) -> list[WorkflowNode]:
    if not ctx.stage_2_output:
        return []
    return list(ctx.stage_2_output.workflow_nodes)


def node_risk_score(ctx: ProjectContext, node: WorkflowNode) -> int:
    """Deterministic node score derived from addressed failure-mode severity."""
    weights = {
        failure_mode.id: _SEVERITY_WEIGHT.get(str(failure_mode.severity).lower(), 0)
        for failure_mode in (ctx.stage_1_output.failure_modes if ctx.stage_1_output else [])
    }
    return sum(
        weights.get(failure_mode_id, 0) for failure_mode_id in node.failure_modes_addressed or []
    )


def required_high_risk_node_ids(
    ctx: ProjectContext, tier: ProjectGateRiskTier | None = None
) -> set[str]:
    """Return workflow node ids that must be covered under *tier*."""
    failure_mode_ids = high_risk_failure_mode_ids(ctx, tier)
    if not failure_mode_ids:
        return set()
    return {
        node.node_id
        for node in _nodes(ctx)
        if failure_mode_ids.intersection(set(node.failure_modes_addressed or []))
    }


def required_node_ids_for_tier(ctx: ProjectContext, tier: ProjectGateRiskTier) -> set[str]:
    """Backward-compatible alias used by gate rules and tests."""
    return required_high_risk_node_ids(ctx, tier)


def _sample_budget(tier: ProjectGateRiskTier) -> int:
    if tier == ProjectGateRiskTier.LOW:
        return settings.stage3_low_risk_sample_nodes
    if tier == ProjectGateRiskTier.MEDIUM:
        return settings.stage3_medium_risk_sample_nodes
    return settings.stage3_high_risk_sample_nodes


def min_cases_for_tier(tier: ProjectGateRiskTier) -> int:
    if tier in {ProjectGateRiskTier.HIGH, ProjectGateRiskTier.CRITICAL}:
        return settings.stage3_min_cases_per_high_risk_node
    return 1


def _ordered_node_ids(ctx: ProjectContext) -> list[str]:
    nodes = _nodes(ctx)
    index_by_id = {node.node_id: index for index, node in enumerate(nodes)}
    scores = {node.node_id: node_risk_score(ctx, node) for node in nodes}
    return sorted(
        [node.node_id for node in nodes],
        key=lambda node_id: (-scores[node_id], index_by_id[node_id]),
    )


def build_coverage_policy(ctx: ProjectContext) -> CoveragePolicy:
    """Build the deterministic Stage 3 target-node policy for *ctx*."""
    assessment = assess_project_risk(ctx)
    tier = assessment.effective_tier
    ordered = _ordered_node_ids(ctx)
    required = required_high_risk_node_ids(ctx, tier)
    required_ordered = [node_id for node_id in ordered if node_id in required]
    min_ratio = float(settings.stage3_min_coverage_ratio)
    min_cases = min_cases_for_tier(tier)

    if not ordered:
        return CoveragePolicy(
            risk_tier=tier,
            required_node_ids=[],
            selected_node_ids=[],
            sample_budget=0,
            min_coverage_ratio=min_ratio,
            min_cases_per_high_risk_node=min_cases,
            rationale="no workflow nodes available",
        )

    if tier == ProjectGateRiskTier.CRITICAL:
        budget = len(ordered)
        rationale = "CRITICAL: select every workflow node"
    else:
        configured = max(_sample_budget(tier), math.ceil(min_ratio * len(ordered)))
        budget = min(len(ordered), max(0, configured))
        rationale = (
            f"{tier.value.upper()}: budget=max(configured_sample={_sample_budget(tier)}, "
            f"ceil({min_ratio}*{len(ordered)}))={budget}; required high-risk nodes always included"
        )

    selected = list(required_ordered)
    for node_id in ordered:
        if len(selected) >= budget:
            break
        if node_id not in required:
            selected.append(node_id)

    return CoveragePolicy(
        risk_tier=tier,
        required_node_ids=required_ordered,
        selected_node_ids=selected,
        sample_budget=budget,
        min_coverage_ratio=min_ratio,
        min_cases_per_high_risk_node=min_cases,
        rationale=rationale,
    )


def select_target_node_ids(ctx: ProjectContext, policy: CoveragePolicy | None = None) -> list[str]:
    """Return the deterministic Stage 3 target node ids."""
    resolved = policy or build_coverage_policy(ctx)
    return list(resolved.selected_node_ids)


def build_coverage_report(ctx: ProjectContext) -> dict:
    """Coverage report shared by gates, readiness and eval summaries."""
    policy = build_coverage_policy(ctx)
    nodes = _nodes(ctx)
    node_case_counts = {
        node.node_id: sum(
            1
            for case in ctx.eval_cases
            if case.stage_id == 3 and case.target_node_id == node.node_id
        )
        for node in nodes
    }
    min_cases = policy.min_cases_per_high_risk_node
    required = set(policy.required_node_ids)
    missing_required = [
        node_id
        for node_id in policy.required_node_ids
        if node_case_counts.get(node_id, 0) < min_cases
    ]
    min_cases_gaps = [
        node_id
        for node_id in policy.required_node_ids
        if node_case_counts.get(node_id, 0) < min_cases
    ]
    covered_required = sorted(
        node_id for node_id in required if node_case_counts.get(node_id, 0) >= min_cases
    )
    coverage_ratio = round(len(covered_required) / len(required), 4) if required else 1.0
    return {
        "policy": policy.as_dict(),
        "required_node_ids": sorted(policy.required_node_ids),
        "selected_node_ids": list(policy.selected_node_ids),
        "eval_case_covered_node_ids": covered_required,
        "missing_required_node_ids": sorted(missing_required),
        "node_case_counts": node_case_counts,
        "min_cases_gaps": sorted(min_cases_gaps),
        "coverage_ratio": coverage_ratio,
    }
