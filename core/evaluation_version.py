# core/evaluation_version.py
"""Evaluation-version snapshot used by approvals, treatments, and eval runs.

A version is composed of two parts:

- ``stage_versions``: the monotonic version of each stage output. Any structured
  edit or regeneration bumps a stage version, so an edit-then-revert sequence
  cannot make an old approval current again.
- ``content_digest``: a hash of the critical evaluation content (project inputs,
  risk inputs, and risk-relevant fields of the four structured stage outputs).

Both are combined into ``digest``. Consumers store the digest and re-evaluate
whether it still matches the current context. Conversation history, traces,
timestamps, and raw summaries are deliberately excluded because they do not
change the evaluated project.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from core.models import ProjectContext
from core.risk.assessment import risk_assessment_digest

EVALUATION_VERSION_SCHEMA = "1.0"


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
        "risk": risk_assessment_digest(ctx),
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
        "content_digest": content_digest,
        "digest": _digest({"stage_versions": stage_versions, "content_digest": content_digest}),
    }


def current_evaluation_version(ctx: ProjectContext) -> dict[str, Any]:
    return build_evaluation_version(ctx)


def current_evaluation_digest(ctx: ProjectContext) -> str:
    return str(build_evaluation_version(ctx)["digest"])
