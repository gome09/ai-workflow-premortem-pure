from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from core.llm.provider import StructuredGenerationRequest, StructuredOutputProvider
from stages.validators import validate_stage1, validate_stage2, validate_stage3, validate_stage4


class StructuredOutputResult(BaseModel):
    parsed: dict[str, Any] | None = None
    raw_text: str
    stage: int | None = None
    schema_name: str = ""
    parser_status: Literal[
        "parsed",
        "validation_failed",
        "non_json",
        "markdown_fallback",
        "retry_exhausted",
        "manual_repair_required",
        "failed",
    ] = "failed"
    parser_detail_status: str = ""
    validation_errors: list[str] = Field(default_factory=list)
    model: str = ""
    prompt_version: str = "0.7.0"
    trace_id: str | None = None
    fallback_used: bool = False
    retry_count: int = 0


class StructuredOutputClient:
    """Provider-neutral stage output parser.

    This adapter is the JSON-first boundary for Stage 1-4. Stage executors still
    own Markdown fallback behavior, but they should enter JSON parsing through
    this client so parser status and trace metadata remain consistent.
    """

    def generate(
        self,
        *,
        stage: int,
        provider: StructuredOutputProvider,
        prompt: str = "",
        messages: list[Any] | None = None,
        output_schema: type | None = None,
        model: str = "",
        temperature: float = 0.0,
        max_retries: int = 0,
        trace_id: str | None = None,
    ) -> StructuredOutputResult:
        """Generate through a provider boundary, then validate with existing schemas.

        Provider runtime validation for non-mock providers remains deferred to
        a future unified provider-validation pass.
        """
        response = provider.generate_structured(
            StructuredGenerationRequest(
                stage=stage,
                prompt=prompt,
                messages=messages or [],
                output_schema=output_schema,
                model=model,
                temperature=temperature,
                max_retries=max_retries,
                trace_id=trace_id,
            )
        )
        return self.parse_stage_output(
            stage,
            response.raw_text,
            model=response.model,
            trace_id=response.trace_id or trace_id,
            retry_count=response.retry_count,
        )

    def parse_stage_output(
        self,
        stage: int,
        raw_text: str,
        *,
        model: str = "",
        trace_id: str | None = None,
        retry_count: int = 0,
    ) -> StructuredOutputResult:
        validators = {
            1: ("Stage1Schema", validate_stage1),
            2: ("Stage2Schema", validate_stage2),
            3: ("Stage3Schema", validate_stage3),
            4: ("Stage4Schema", validate_stage4),
        }
        item = validators.get(stage)
        if item is None:
            return StructuredOutputResult(
                raw_text=raw_text,
                stage=stage,
                model=model,
                trace_id=trace_id,
                retry_count=retry_count,
                validation_errors=[f"Unsupported stage: {stage}"],
                parser_status="failed",
            )

        schema_name, validator = item
        try:
            schema = validator(raw_text)
            return StructuredOutputResult(
                parsed=schema.model_dump(mode="json"),
                raw_text=raw_text,
                stage=stage,
                schema_name=schema_name,
                parser_status="parsed",
                model=model,
                trace_id=trace_id,
                retry_count=retry_count,
            )
        except Exception as exc:  # noqa: BLE001 - adapter returns structured parse metadata
            message = str(exc)
            status: Literal["validation_failed", "non_json"] = (
                "non_json" if "未找到可解析的 JSON 对象" in message else "validation_failed"
            )
            return StructuredOutputResult(
                raw_text=raw_text,
                stage=stage,
                schema_name=schema_name,
                model=model,
                trace_id=trace_id,
                retry_count=retry_count,
                parser_status=status,
                validation_errors=[message],
            )
