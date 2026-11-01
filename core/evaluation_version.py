# core/evaluation_version.py
"""Evaluation-version snapshot used by approvals, treatments, and eval runs.

A version has two layers:

- ``stage_versions`` / ``input_versions``: monotonic revision counters. Any
  structured stage edit or regeneration bumps a stage version; adding user
  materials or changing the declared target deployment bumps an input version.
  An edit-then-revert sequence therefore cannot make old evidence current again.
- ``content_digest``: a hash of the critical evaluation content: project inputs,
  risk inputs, target deployment, policy versions, the four stage outputs, and
  the current EvalCase definitions (including ``standard_version``).

Evidence is deliberately excluded from the version digest: ``eval_runs``,
``eval_judgments``, ``human_calibrations``, ``risk_treatments``,
``project_approvals``, report artifacts, audit events, traces, conversation
history and timestamps. This avoids a circular dependency where adding the run
that proves a version would change the version being proven. Release validity
is computed separately from the current evidence snapshot in
``core/release_evidence.py``.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from core.models import EvalCase, ProjectContext
from core.risk.assessment import risk_assessment_digest

EVALUATION_VERSION_SCHEMA = "2.0"

INPUT_VERSION_KEY_MATERIALS = "materials"
INPUT_VERSION_KEY_TARGET_DEPLOYMENT = "target_deployment"


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _text_digest(value: str | None) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _stage_versions(ctx: ProjectContext) -> dict[str, int]:
    return {
        f"stage_{stage}": int(ctx.stage_output_versions.get(f"stage_{stage}", 1))
        for stage in range(1, 5)
    }


def bump_input_version(ctx: ProjectContext, key: str) -> int:
    """Increment a monotonic non-stage input version and return the new value."""
    value = int((ctx.input_versions or {}).get(key, 0)) + 1
    ctx.input_versions[key] = value
    return value


def eval_case_digest(case: EvalCase) -> str:
    """Stable digest of one EvalCase definition (outcome fields excluded)."""
    return _digest(
        {
            "eval_id": case.eval_id,
            "stage_id": case.stage_id,
            "target_node_id": case.target_node_id,
            "scenario_type": case.scenario_type,
            "input_payload": _text_digest(case.input_payload),
            "expected_behavior": _text_digest(case.expected_behavior),
            "pass_criteria": list(case.pass_criteria or []),
            "covered_failure_mode_ids": sorted(case.covered_failure_mode_ids or []),
            "standard_version": case.standard_version,
        }
    )


def _policy_content() -> dict[str, Any]:
    # Local imports keep the risk/coverage packages free of evaluation imports.
    from core.coverage.policy import COVERAGE_POLICY_VERSION
    from core.gates.rules.manifest import RULE_MANIFEST
    from core.risk.rules import RISK_MODEL_VERSION

    return {
        "rule_versions": {rule_id: meta.version for rule_id, meta in sorted(RULE_MANIFEST.items())},
        "risk_model_version": RISK_MODEL_VERSION,
        "coverage_policy_version": COVERAGE_POLICY_VERSION,
    }


def _target_deployment_content(ctx: ProjectContext) -> dict[str, Any] | None:
    deployment = ctx.target_deployment
    if deployment is None:
        return None
    return {"endpoint": deployment.endpoint, "version": deployment.version}


def _critical_content(ctx: ProjectContext) -> dict[str, Any]:
    stage_1 = ctx.stage_1_output
    failure_modes = (
        [
            [
                fm.id,
                str(fm.severity),
                fm.category,
                sorted(fm.evidence_ids or []),
            ]
            for fm in stage_1.failure_modes
        ]
        if stage_1
        else []
    )

    stage_2 = ctx.stage_2_output
    workflow_nodes = (
        [
            [
                node.node_id,
                node.stage_name,
                node.model_assigned,
                _text_digest(node.prompt_template),
            ]
            for node in stage_2.workflow_nodes
        ]
        if stage_2
        else []
    )

    stage_3 = ctx.stage_3_output
    test_results = (
        [
            [
                result.tested_node_id,
                result.scenario_type,
                _text_digest(result.test_input),
                list(result.pass_criteria or []),
            ]
            for result in stage_3.test_results
        ]
        if stage_3
        else []
    )

    stage_4 = ctx.stage_4_output
    trigger_methods = (
        [
            [method.node_id, method.model_or_mode, method.trigger_instruction]
            for method in stage_4.trigger_methods
        ]
        if stage_4
        else []
    )

    return {
        "project": [
            ctx.research_target,
            ctx.domain,
            ctx.goal,
            ctx.data_classification,
            ctx.selected_scenario_id,
        ],
        "user_materials": [_text_digest(material) for material in ctx.user_materials],
        "input_versions": dict(ctx.input_versions or {}),
        "target_deployment": _target_deployment_content(ctx),
        "policy": _policy_content(),
        "risk": risk_assessment_digest(ctx),
        "eval_cases": [
            [case.eval_id, eval_case_digest(case)]
            for case in sorted(ctx.eval_cases, key=lambda item: item.eval_id)
        ],
        "stage_1": failure_modes,
        "stage_2": workflow_nodes,
        "stage_3": test_results,
        "stage_4": trigger_methods,
    }


def build_evaluation_version(ctx: ProjectContext) -> dict[str, Any]:
    """Return the full evaluation-version payload (stable and JSON-safe)."""
    stage_versions = _stage_versions(ctx)
    content_digest = _digest(_critical_content(ctx))
    return {
        "schema": EVALUATION_VERSION_SCHEMA,
        "stage_versions": stage_versions,
        "input_versions": dict(ctx.input_versions or {}),
        "content_digest": content_digest,
        "digest": _digest(
            {
                "stage_versions": stage_versions,
                "input_versions": dict(ctx.input_versions or {}),
                "content_digest": content_digest,
            }
        ),
    }


def current_evaluation_version(ctx: ProjectContext) -> dict[str, Any]:
    return build_evaluation_version(ctx)


def current_evaluation_digest(ctx: ProjectContext) -> str:
    return str(build_evaluation_version(ctx)["digest"])
