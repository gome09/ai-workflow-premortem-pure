"""v0.7 StructuredOutputClient tests for later unified validation."""

from __future__ import annotations

import json

from core.llm.structured_output import StructuredOutputClient


def test_structured_output_client_parses_stage1_json():
    raw = json.dumps(
        {
            "failure_modes": [
                {
                    "id": "FM-1",
                    "category": "hallucination",
                    "description": "Unsupported legal claim",
                    "severity": "high",
                    "evidence_ids": [],
                    "evidence": "fixture",
                }
            ],
            "direct_conclusion": "Needs review",
        }
    )

    result = StructuredOutputClient().parse_stage_output(1, raw)

    assert result.parser_status == "parsed"
    assert result.parsed is not None


def test_structured_output_client_marks_non_json():
    result = StructuredOutputClient().parse_stage_output(1, "not json")

    assert result.parser_status in {"non_json", "validation_failed"}
    assert result.validation_errors
