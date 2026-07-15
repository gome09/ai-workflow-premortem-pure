"""Wave 2 集成测试：mapper.py 三表聚合接入。

验证 NIST AI 600-1 / OWASP Agentic 2026 / TC260 三张新标签表
已正确接入 refs_for_risk_type / refs_for_attack_type 聚合链路。
"""

from types import SimpleNamespace

from tools.taxonomies.mapper import (
    apply_taxonomy_to_redteam_case,
    apply_taxonomy_to_safety_finding,
    refs_for_attack_type,
    refs_for_risk_type,
)

# ── refs_for_risk_type 聚合验证 ───────────────────────────────────────────────


def test_refs_for_risk_type_prompt_injection_includes_nist_gai_and_asi():
    """prompt_injection 应同时含 NIST AI 600-1 动作项 + OWASP ASI 标签。"""
    refs = refs_for_risk_type("prompt_injection")
    assert "NIST_AI_600_1:MS-2.7-008" in refs
    assert "OWASP_ASI_2026:ASI01" in refs


def test_refs_for_risk_type_over_autonomy_includes_asi_and_tc260():
    """over_autonomy 应含 OWASP ASI03 + TC260 MIN_PRIVILEGE/HUMAN_OVERSIGHT。"""
    refs = refs_for_risk_type("over_autonomy")
    assert "OWASP_ASI_2026:ASI03" in refs
    assert "TC260_AGENT:MIN_PRIVILEGE" in refs
    assert "TC260_AGENT:HUMAN_OVERSIGHT" in refs


def test_refs_for_risk_type_unbounded_consumption_includes_nist_gai_and_tc260():
    """unbounded_consumption 应含 NIST AI 600-1 + TC260（ASI 已删除此映射，不应含 ASI07）。"""
    refs = refs_for_risk_type("unbounded_consumption")
    assert "NIST_AI_600_1:MS-2.11-001" in refs
    assert "TC260_AGENT:RESOURCE_LIMIT" in refs
    # ASI07 非 Resource Abuse，已删除此映射
    asi_refs = [r for r in refs if r.startswith("OWASP_ASI_2026:")]
    assert "OWASP_ASI_2026:ASI07" not in asi_refs


def test_refs_for_risk_type_system_prompt_leakage_includes_all_three():
    """system_prompt_leakage 应同时含三张新表的标签。"""
    refs = refs_for_risk_type("system_prompt_leakage")
    assert "NIST_AI_600_1:MS-2.7-008" in refs
    assert "OWASP_ASI_2026:ASI01" in refs
    assert "TC260_AGENT:SENSITIVE_DATA_MINIMAL" in refs


def test_refs_for_risk_type_improper_output_handling_includes_nist_gai():
    refs = refs_for_risk_type("improper_output_handling")
    assert "NIST_AI_600_1:MS-2.5-005" in refs


def test_refs_for_risk_type_unknown_returns_empty():
    assert refs_for_risk_type("nonexistent_risk_type") == []


def test_refs_for_risk_type_none_returns_empty():
    assert refs_for_risk_type(None) == []


def test_refs_for_risk_type_no_duplicates():
    """聚合后不应有重复 ref。"""
    refs = refs_for_risk_type("prompt_injection")
    assert len(refs) == len(set(refs)), "refs_for_risk_type 返回值含重复"


# ── refs_for_attack_type 聚合验证 ──────────────────────────────────────────────


def test_refs_for_attack_type_direct_prompt_injection_includes_asi01():
    refs = refs_for_attack_type("direct_prompt_injection")
    assert "OWASP_ASI_2026:ASI01" in refs


def test_refs_for_attack_type_indirect_prompt_injection_includes_asi01():
    refs = refs_for_attack_type("indirect_prompt_injection")
    assert "OWASP_ASI_2026:ASI01" in refs


def test_refs_for_attack_type_tool_overreach_includes_asi02():
    refs = refs_for_attack_type("tool_overreach")
    assert "OWASP_ASI_2026:ASI02" in refs


def test_refs_for_attack_type_source_poisoning_includes_asi06():
    refs = refs_for_attack_type("source_poisoning")
    assert "OWASP_ASI_2026:ASI06" in refs


def test_refs_for_attack_type_none_returns_empty():
    assert refs_for_attack_type(None) == []


# ── apply_taxonomy_to_redteam_case 集成验证 ────────────────────────────────────


def test_apply_taxonomy_to_redteam_case_emits_asi_label():
    """红队用例 attack_type=direct_prompt_injection 应带出 ASI01 标签。"""
    case = SimpleNamespace(
        attack_type="direct_prompt_injection",
        taxonomy_refs=[],
        control_refs=[],
    )
    apply_taxonomy_to_redteam_case(case)
    assert "OWASP_ASI_2026:ASI01" in case.taxonomy_refs


def test_apply_taxonomy_to_redteam_case_preserves_existing_refs():
    """已有 taxonomy_refs 不应丢失。"""
    case = SimpleNamespace(
        attack_type="direct_prompt_injection",
        taxonomy_refs=["CUSTOM:PRE_EXISTING"],
        control_refs=[],
    )
    apply_taxonomy_to_redteam_case(case)
    assert "CUSTOM:PRE_EXISTING" in case.taxonomy_refs
    assert "OWASP_ASI_2026:ASI01" in case.taxonomy_refs


# ── apply_taxonomy_to_safety_finding 集成验证 ──────────────────────────────────


def test_apply_taxonomy_to_safety_finding_emits_nist_gai_and_tc260():
    """finding risk_type=unbounded_consumption 应带出 NIST AI 600-1 + TC260 标签。"""
    finding = SimpleNamespace(
        risk_type="unbounded_consumption",
        taxonomy_refs=[],
        control_refs=[],
        mitigation_status="",
        residual_risk="unknown",
        severity="medium",
        status=None,
    )
    apply_taxonomy_to_safety_finding(finding)
    assert "NIST_AI_600_1:MS-2.11-001" in finding.taxonomy_refs
    assert "TC260_AGENT:RESOURCE_LIMIT" in finding.taxonomy_refs


def test_apply_taxonomy_to_safety_finding_emits_asi_for_over_autonomy():
    finding = SimpleNamespace(
        risk_type="over_autonomy",
        taxonomy_refs=[],
        control_refs=[],
        mitigation_status="",
        residual_risk="unknown",
        severity="high",
        status=None,
    )
    apply_taxonomy_to_safety_finding(finding)
    assert "OWASP_ASI_2026:ASI03" in finding.taxonomy_refs
