from stages.validators import extract_json_object, stage1_schema_to_output, validate_stage1


def test_extract_json_from_markdown_block():
    raw = '```json\n{"direct_conclusion":"ok","failure_modes":[]}\n```'
    assert extract_json_object(raw) == {"direct_conclusion": "ok", "failure_modes": []}


def test_stage1_json_to_output_supports_critical():
    raw = """{
      "failure_modes": [{
        "id": "FM1",
        "category": "幻觉",
        "description": "关键事实错误",
        "severity": "critical",
        "evidence": "资料A",
        "requires_human_review": true
      }],
      "direct_conclusion": "需要人工监督",
      "open_questions": []
    }"""
    schema = validate_stage1(raw)
    output = stage1_schema_to_output(schema, raw)
    assert output.failure_modes[0].severity == "critical"
    assert output.failure_modes[0].needs_verification is True
