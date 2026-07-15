# tests/test_scenario_semantic_integrity.py
"""WS-7: Scenario semantic integrity checks.

Verifies that each built-in scenario fixture contains domain-appropriate
failure-mode categories and that the manifest's ``mock_fixture`` field matches
the fixture module name. Importing the fixture modules directly (rather than
going through the LLM adapter) keeps these tests deterministic and fast.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.llm.adapters.mock_fixtures import (
    generic_rag_demo,
    university_mental_health,
)
from scenarios.registry import _MANIFEST_DIR, get_scenario


def _failure_modes(fixture_module) -> list[dict]:
    """Parse the Stage 1 fixture response and return its failure_modes list."""
    raw = fixture_module.stage_1_response()
    data = json.loads(raw)
    return list(data.get("failure_modes", []))


def _categories(fixture_module) -> list[str]:
    return [str(fm.get("category", "")) for fm in _failure_modes(fixture_module)]


def _join_text(fixture_module) -> str:
    """Concatenate category + description for substring checks."""
    parts: list[str] = []
    for fm in _failure_modes(fixture_module):
        parts.append(str(fm.get("category", "")))
        parts.append(str(fm.get("description", "")))
    return " ".join(parts)


# ─────────────────────────────────────────────
# university_mental_health
# ─────────────────────────────────────────────


def test_university_mental_health_contains_crisis_risks():
    text = _join_text(university_mental_health)
    # Crisis / self-harm / underreporting / diagnosis / privacy risks
    assert "自伤" in text or "他伤" in text, "must cover self-harm/other-harm signals"
    assert "漏报" in text, "must cover crisis underreporting"
    assert "诊断" in text, "must cover unauthorized diagnosis"
    assert "隐私" in text or "敏感信息" in text, "must cover privacy / sensitive info"


def test_university_mental_health_no_academic_integrity_risk():
    text = _join_text(university_mental_health)
    # Mental-health scenario must NOT frame risks around academic integrity
    assert "学术诚信" not in text
    assert "代写" not in text


def test_university_mental_health_has_critical_failure_modes():
    fms = _failure_modes(university_mental_health)
    severities = [str(fm.get("severity", "")).lower() for fm in fms]
    assert "critical" in severities, "must contain at least one critical FM"


# ─────────────────────────────────────────────
# generic_rag_demo
# ─────────────────────────────────────────────


def test_generic_rag_demo_contains_rag_risks():
    text = _join_text(generic_rag_demo)
    # Hallucination / citation / permission / Prompt Injection
    assert "幻觉" in text, "must cover hallucination"
    assert "引用" in text, "must cover citation errors"
    assert "权限" in text or "租户" in text, "must cover permission / tenant isolation"
    assert "Prompt Injection" in text or "注入" in text, "must cover Prompt Injection"


def test_generic_rag_demo_has_critical_fm():
    fms = _failure_modes(generic_rag_demo)
    severities = [str(fm.get("severity", "")).lower() for fm in fms]
    assert "critical" in severities, "must contain at least one critical FM"


# ─────────────────────────────────────────────
# Manifest ↔ fixture module consistency
# ─────────────────────────────────────────────


def test_manifest_mock_fixture_matches_module_name():
    expected = {
        "generic_rag_demo": "generic_rag_demo",
        "university_mental_health": "university_mental_health",
    }
    for scenario_id, expected_fixture in expected.items():
        scenario = get_scenario(scenario_id)
        assert scenario.mock_fixture == expected_fixture, (
            f"{scenario_id}: manifest mock_fixture={scenario.mock_fixture!r} "
            f"expected {expected_fixture!r}"
        )


def test_all_manifests_exist_on_disk():
    expected_ids = {
        "generic_rag_demo",
        "university_mental_health",
    }
    found_ids = {p.stem for p in Path(_MANIFEST_DIR).glob("*.json")}
    assert expected_ids.issubset(found_ids), (
        f"missing manifests: {sorted(expected_ids - found_ids)}"
    )
