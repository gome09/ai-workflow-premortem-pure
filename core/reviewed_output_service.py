# core/reviewed_output_service.py
from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from core.models import (
    ProjectContext,
    Stage1Output,
    Stage2Output,
    Stage3Output,
    Stage4Output,
)
from stages.schemas import Stage1Schema, Stage2Schema, Stage3Schema, Stage4Schema
from stages.validators import (
    stage1_schema_to_output,
    stage2_schema_to_output,
    stage3_schema_to_output,
    stage4_schema_to_output,
)


class ReviewedOutputError(ValueError):
    """人工编辑后的结构化输出无法应用。"""


class ReviewedOutputApplyResult(BaseModel):
    """Result metadata for applying a human-reviewed stage output."""

    applied_to_structured_output: bool = False
    stage_id: int
    stage_output_version_before: int
    stage_output_version_after: int
    parser_error_cleared: bool = False
    reviewed_key: str
    warnings: list[str] = Field(default_factory=list)


def _extract_structured_payload(payload_after: dict[str, Any]) -> dict[str, Any] | None:
    """兼容 structured_output 包裹和直接提交完整 stage schema 两种格式。"""
    if not payload_after:
        return None
    structured = payload_after.get("structured_output")
    if isinstance(structured, dict):
        return structured
    stage_schema_markers = {"failure_modes", "workflow_nodes", "test_cases", "trigger_methods"}
    if any(key in payload_after for key in stage_schema_markers):
        return payload_after
    return None


def apply_reviewed_output_with_result(
    ctx: ProjectContext,
    stage: int,
    payload_after: dict[str, Any],
) -> ReviewedOutputApplyResult:
    """Apply reviewed payload atomically and return explicit metadata.

    Structured stage payload is validated and converted before any ProjectContext
    mutation. This prevents failed human edits from polluting reviewed_outputs
    or clearing parser_errors.
    """
    reviewed_key = f"stage_{stage}"
    version_before = int(ctx.stage_output_versions.get(reviewed_key, 1))
    parser_error_existed = reviewed_key in ctx.parser_errors
    payload_to_store = deepcopy(payload_after or {})
    result = ReviewedOutputApplyResult(
        stage_id=stage,
        stage_output_version_before=version_before,
        stage_output_version_after=version_before,
        reviewed_key=reviewed_key,
    )

    structured = _extract_structured_payload(payload_to_store)
    if structured is None:
        payload_to_store["_applied_to_structured_output"] = False
        result.warnings.append("payload_after did not contain a complete structured stage schema")
        ctx.reviewed_outputs[reviewed_key] = payload_to_store
        return result

    raw_text = payload_to_store.get("edited_text") or payload_to_store.get("raw_summary") or ""
    # schema/new_output are rebound per mutually-exclusive stage branch; union-annotate
    # so mypy narrows each branch independently instead of pinning to the Stage 1 types.
    schema: Stage1Schema | Stage2Schema | Stage3Schema | Stage4Schema
    new_output: Stage1Output | Stage2Output | Stage3Output | Stage4Output
    try:
        if stage == 1:
            schema = Stage1Schema.model_validate(structured)
            search_sources = ctx.stage_1_output.search_sources if ctx.stage_1_output else []
            new_output = stage1_schema_to_output(schema, raw_text, search_sources=search_sources)
            target_attr = "stage_1_output"
        elif stage == 2:
            schema = Stage2Schema.model_validate(structured)
            new_output = stage2_schema_to_output(schema, raw_text)
            target_attr = "stage_2_output"
        elif stage == 3:
            schema = Stage3Schema.model_validate(structured)
            new_output = stage3_schema_to_output(schema, raw_text)
            target_attr = "stage_3_output"
        elif stage == 4:
            schema = Stage4Schema.model_validate(structured)
            new_output = stage4_schema_to_output(schema, raw_text)
            target_attr = "stage_4_output"
        else:
            raise ReviewedOutputError(f"Unsupported stage: {stage}")
    except ValidationError as exc:
        raise ReviewedOutputError(
            f"Reviewed structured_output failed schema validation: {exc}"
        ) from exc

    payload_to_store["_applied_to_structured_output"] = True
    setattr(ctx, target_attr, new_output)
    ctx.reviewed_outputs[reviewed_key] = payload_to_store
    result.applied_to_structured_output = True
    ctx.parser_errors.pop(reviewed_key, None)
    result.parser_error_cleared = parser_error_existed
    return result


def apply_reviewed_output(
    ctx: ProjectContext, stage: int, payload_after: dict[str, Any]
) -> ProjectContext:
    """Backward-compatible wrapper for older call sites/tests."""
    apply_reviewed_output_with_result(ctx, stage, payload_after)
    return ctx
