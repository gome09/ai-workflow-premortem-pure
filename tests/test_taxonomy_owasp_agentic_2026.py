"""T2.3 OWASP Agentic Applications Top 10 2026 标签表测试。

注意：本测试只 import owasp_agentic_2026.py，不 import mapper.py。
聚合接入测试在 Wave 2 阶段补充。
"""

import re

from tools.taxonomies.owasp_agentic_2026 import ASI_ATTACK_REFS, ASI_RISK_REFS

ASI_PATTERN = re.compile(r"^OWASP_ASI_2026:ASI\d{2}$")


def test_asi_attack_refs_format():
    """所有 ASI_ATTACK_REFS 的 ref 必须形如 OWASP_ASI_2026:ASI\d{2}。"""
    for attack_type, refs in ASI_ATTACK_REFS.items():
        for ref in refs:
            assert ASI_PATTERN.match(ref), f"attack_type={attack_type} 的 ref={ref} 不符合格式"


def test_asi_risk_refs_format():
    """所有 ASI_RISK_REFS 的 ref 必须形如 OWASP_ASI_2026:ASI\d{2}。"""
    for risk_type, refs in ASI_RISK_REFS.items():
        for ref in refs:
            assert ASI_PATTERN.match(ref), f"risk_type={risk_type} 的 ref={ref} 不符合格式"


def test_asi_attack_refs_covers_prompt_injection():
    """direct_prompt_injection 与 indirect_prompt_injection 都映射到 ASI01。"""
    assert "OWASP_ASI_2026:ASI01" in ASI_ATTACK_REFS.get("direct_prompt_injection", [])
    assert "OWASP_ASI_2026:ASI01" in ASI_ATTACK_REFS.get("indirect_prompt_injection", [])


def test_asi_attack_refs_covers_tool_overreach():
    """tool_overreach 映射到 ASI02。"""
    assert "OWASP_ASI_2026:ASI02" in ASI_ATTACK_REFS.get("tool_overreach", [])


def test_asi_attack_refs_covers_excessive_agency():
    """excessive_agency 与 unsafe_autonomy 都映射到 ASI03。"""
    assert "OWASP_ASI_2026:ASI03" in ASI_ATTACK_REFS.get("excessive_agency", [])
    assert "OWASP_ASI_2026:ASI03" in ASI_ATTACK_REFS.get("unsafe_autonomy", [])


def test_asi_attack_refs_covers_source_poisoning():
    """source_poisoning 映射到 ASI06。"""
    assert "OWASP_ASI_2026:ASI06" in ASI_ATTACK_REFS.get("source_poisoning", [])


def test_asi_risk_refs_covers_prompt_injection():
    assert "OWASP_ASI_2026:ASI01" in ASI_RISK_REFS.get("prompt_injection", [])


def test_asi_risk_refs_covers_over_autonomy():
    assert "OWASP_ASI_2026:ASI03" in ASI_RISK_REFS.get("over_autonomy", [])


def test_asi_risk_refs_covers_system_prompt_leakage():
    """LLM07 衍生 risk_type 也应有 ASI 映射。"""
    assert "OWASP_ASI_2026:ASI01" in ASI_RISK_REFS.get("system_prompt_leakage", [])


def test_asi_risk_refs_covers_policy_gap():
    assert "OWASP_ASI_2026:ASI09" in ASI_RISK_REFS.get("policy_gap", [])


def test_asi_refs_not_empty():
    """任何映射的 refs 列表不能为空。"""
    for k, refs in ASI_ATTACK_REFS.items():
        assert refs, f"ASI_ATTACK_REFS[{k}] 为空"
    for k, refs in ASI_RISK_REFS.items():
        assert refs, f"ASI_RISK_REFS[{k}] 为空"


def test_asi_attack_refs_no_unrelated_types_force_mapped():
    """secret_exfiltration / fake_citation / unsupported_claim 不应被强行映射（无直接 ASI 对应）。"""
    for k in ["secret_exfiltration", "fake_citation", "unsupported_claim"]:
        assert k not in ASI_ATTACK_REFS, (
            f"{k} 不应出现在 ASI_ATTACK_REFS（无直接 ASI 对应，宁缺毋滥）"
        )
