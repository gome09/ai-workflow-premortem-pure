# tests/test_domain_labels_production.py
"""
T2.5 验收测试：领域扩展标签接入生产链路。

验证 apply_taxonomy_to_safety_finding 在 domain 参数透传后：
  1. university_ai 域 + domain-specific risk_type → refs 含 PIPL 标签
  2. university_ai 域 + 标准 risk_type → refs 仍含 OWASP（回退不丢）
  3. default 域 + 标准 risk_type → 与旧逻辑完全一致（向后兼容）
  4. medical_ai 域 + domain-specific risk_type → refs 含 HIPAA-PHI
  5. medical_ai 域 + 标准 risk_type → refs 仍含 OWASP（回退不丢）
  6. unknown 域 + 标准 risk_type → 同 default（不丢标签）
  7. 集成 _finding（safety_classifier）：university_ai ctx + 标准 risk_type → OWASP refs 保留
  8. 集成 _finding（safety_classifier）：default ctx + 标准 risk_type → 与旧逻辑一致

注意：SafetyFinding.risk_type Literal 不含 domain-specific 值（student_data_privacy 等），
因此直接测试 apply_taxonomy_to_safety_finding 时用 SimpleNamespace 绕过 pydantic 校验；
集成测试 _finding 时只用标准 risk_type（Literal 允许的值），验证 domain 参数透传与回退路径。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from core.models import ProjectContext
from tools.taxonomies.mapper import (
    apply_taxonomy_to_safety_finding,
    controls_for_risk_type,
    refs_for_risk_type,
)


def _make_finding(risk_type: str | None = None, **kwargs: Any) -> SimpleNamespace:
    """构造最小 finding mock，绕过 SafetyFinding.risk_type Literal 校验。

    用于直接测试 apply_taxonomy_to_safety_finding 的 domain 叠加行为，
    覆盖 domain-specific risk_type（如 student_data_privacy）路径。
    """
    defaults: dict[str, Any] = {
        "taxonomy_refs": [],
        "control_refs": [],
        "risk_type": risk_type,
        "mitigation_status": "open",
        "residual_risk": "unknown",
        "status": None,
        "severity": "medium",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_ctx(domain_profile: str = "default") -> ProjectContext:
    """构造带 domain_profile 的 ProjectContext。"""
    return ProjectContext(
        session_id="t25-test",
        project_name="t25-domain-labels",
        scenario_config={"domain_profile": domain_profile},
    )


# ── 直接测试 apply_taxonomy_to_safety_finding 的 domain 分发 ─────────────────


class TestApplyTaxonomyDomainDispatch:
    """验证 domain 参数命中 university_ai/medical_ai 时叠加领域专属标签。"""

    def test_university_ai_with_student_data_privacy_adds_pipl_refs(self):
        finding = _make_finding("student_data_privacy")
        result = apply_taxonomy_to_safety_finding(finding, domain="university_ai")
        assert "PIPL:Article_28_Sensitive_Personal_Info" in result.taxonomy_refs

    def test_university_ai_with_student_data_privacy_adds_data_minimization_control(self):
        finding = _make_finding("student_data_privacy")
        result = apply_taxonomy_to_safety_finding(finding, domain="university_ai")
        assert "CONTROL:DATA_MINIMIZATION" in result.control_refs

    def test_university_ai_with_academic_integrity_adds_genai_ref(self):
        finding = _make_finding("academic_integrity")
        result = apply_taxonomy_to_safety_finding(finding, domain="university_ai")
        assert "GENAI:Article_11_Education_Content" in result.taxonomy_refs

    def test_university_ai_with_standard_prompt_injection_still_has_owasp(self):
        finding = _make_finding("prompt_injection")
        result = apply_taxonomy_to_safety_finding(finding, domain="university_ai")
        # prompt_injection 不在 UNIV_RISK_REFS 中 → 回退到标准 refs（含 OWASP）
        assert any("OWASP" in ref for ref in result.taxonomy_refs)

    def test_university_ai_with_standard_prompt_injection_matches_default(self):
        """标准 risk_type 在 university_ai 下回退后应与 default 完全一致。"""
        finding_univ = _make_finding("prompt_injection")
        result_univ = apply_taxonomy_to_safety_finding(finding_univ, domain="university_ai")
        finding_default = _make_finding("prompt_injection")
        result_default = apply_taxonomy_to_safety_finding(finding_default, domain="default")
        assert set(result_univ.taxonomy_refs) == set(result_default.taxonomy_refs)

    def test_medical_ai_with_patient_data_privacy_adds_hipaa_phi(self):
        finding = _make_finding("patient_data_privacy")
        result = apply_taxonomy_to_safety_finding(finding, domain="medical_ai")
        assert "HIPAA-PHI" in result.taxonomy_refs

    def test_medical_ai_with_patient_data_privacy_adds_hipaa_control(self):
        finding = _make_finding("patient_data_privacy")
        result = apply_taxonomy_to_safety_finding(finding, domain="medical_ai")
        assert "HIPAA-164.514" in result.control_refs

    def test_medical_ai_with_misdiagnosis_risk_adds_fda_samd(self):
        finding = _make_finding("misdiagnosis_risk")
        result = apply_taxonomy_to_safety_finding(finding, domain="medical_ai")
        assert "FDA-SaMD-2021" in result.taxonomy_refs

    def test_medical_ai_with_standard_prompt_injection_still_has_owasp(self):
        finding = _make_finding("prompt_injection")
        result = apply_taxonomy_to_safety_finding(finding, domain="medical_ai")
        assert any("OWASP" in ref for ref in result.taxonomy_refs)

    def test_default_domain_matches_old_behavior_for_prompt_injection(self):
        finding = _make_finding("prompt_injection")
        result = apply_taxonomy_to_safety_finding(finding, domain="default")
        expected_refs = refs_for_risk_type("prompt_injection")
        assert set(result.taxonomy_refs) == set(expected_refs)

    def test_default_domain_matches_old_behavior_for_sensitive_info(self):
        finding = _make_finding("sensitive_info")
        result = apply_taxonomy_to_safety_finding(finding, domain="default")
        expected_refs = refs_for_risk_type("sensitive_info")
        assert set(result.taxonomy_refs) == set(expected_refs)

    def test_default_domain_matches_old_behavior_for_controls(self):
        finding = _make_finding("prompt_injection")
        result = apply_taxonomy_to_safety_finding(finding, domain="default")
        expected_controls = controls_for_risk_type("prompt_injection")
        assert set(result.control_refs) == set(expected_controls)

    def test_unknown_domain_falls_back_to_default(self):
        finding = _make_finding("prompt_injection")
        result = apply_taxonomy_to_safety_finding(finding, domain="some_unknown_profile")
        # unknown domain 不在 {"university_ai","medical_ai"} 集合中 → 行为同 default
        expected_refs = refs_for_risk_type("prompt_injection")
        assert set(result.taxonomy_refs) == set(expected_refs)

    def test_none_risk_type_with_university_domain_returns_empty_refs(self):
        finding = _make_finding(None)
        result = apply_taxonomy_to_safety_finding(finding, domain="university_ai")
        # None → refs_for_risk_type(None) 返回 []；refs_for_risk_type_extended(None, "university_ai") 回退也返回 []
        assert result.taxonomy_refs == []

    def test_existing_refs_preserved_when_domain_adds_more(self):
        finding = _make_finding(
            "student_data_privacy", taxonomy_refs=["EXISTING_REF"], control_refs=["EXISTING_CTRL"]
        )
        result = apply_taxonomy_to_safety_finding(finding, domain="university_ai")
        assert "EXISTING_REF" in result.taxonomy_refs
        assert "PIPL:Article_28_Sensitive_Personal_Info" in result.taxonomy_refs
        assert "EXISTING_CTRL" in result.control_refs
        assert "CONTROL:DATA_MINIMIZATION" in result.control_refs

    def test_idempotent_no_duplicate_refs_on_second_call(self):
        finding = _make_finding("student_data_privacy")
        apply_taxonomy_to_safety_finding(finding, domain="university_ai")
        first_refs = list(finding.taxonomy_refs)
        first_controls = list(finding.control_refs)
        apply_taxonomy_to_safety_finding(finding, domain="university_ai")
        # 第二次调用应当幂等（去重后不变）
        assert finding.taxonomy_refs == first_refs
        assert finding.control_refs == first_controls


# ── 集成测试：生产调用链路 domain 透传 ───────────────────────────────────────


class TestProductionCallSiteIntegration:
    """验证 _finding (safety_classifier) 的 domain 透传。

    SafetyFinding.risk_type Literal 不含 domain-specific 值，
    因此集成测试只用标准 risk_type，验证 domain 参数正确透传且回退路径不丢标签。
    """

    def test_finding_helper_under_university_ai_keeps_owasp_for_prompt_injection(self):
        from tools.safety_classifier import _finding

        ctx = _make_ctx("university_ai")
        finding = _finding(
            ctx,
            stage_id=1,
            risk_type="prompt_injection",
            severity="high",
            location="user_materials[0]",
            description="prompt injection attempt",
            recommended_action="人工检查",
        )
        # university_ai + prompt_injection（标准 risk_type）→ 回退到标准 refs，OWASP 不丢
        assert any("OWASP" in ref for ref in finding.taxonomy_refs)

    def test_finding_helper_under_default_matches_standard_refs(self):
        from tools.safety_classifier import _finding

        ctx = _make_ctx("default")
        finding = _finding(
            ctx,
            stage_id=1,
            risk_type="prompt_injection",
            severity="high",
            location="user_materials[0]",
            description="prompt injection attempt",
            recommended_action="人工检查",
        )
        expected = set(refs_for_risk_type("prompt_injection"))
        assert set(finding.taxonomy_refs) == expected

    def test_finding_helper_under_medical_ai_keeps_owasp_for_prompt_injection(self):
        from tools.safety_classifier import _finding

        ctx = _make_ctx("medical_ai")
        finding = _finding(
            ctx,
            stage_id=1,
            risk_type="prompt_injection",
            severity="high",
            location="user_materials[0]",
            description="prompt injection attempt",
            recommended_action="人工检查",
        )
        assert any("OWASP" in ref for ref in finding.taxonomy_refs)

    def test_finding_helper_under_university_ai_keeps_nist_gai_for_prompt_injection(self):
        """验证 Wave 2 接入的 NIST_GAI 标签在 university_ai 回退路径中仍可达。"""
        from tools.safety_classifier import _finding

        ctx = _make_ctx("university_ai")
        finding = _finding(
            ctx,
            stage_id=1,
            risk_type="prompt_injection",
            severity="high",
            location="user_materials[0]",
            description="prompt injection attempt",
            recommended_action="人工检查",
        )
        # NIST_GAI_ACTION_REFS 中 prompt_injection 映射到 NIST_AI_600_1:MS-2.7-008
        assert "NIST_AI_600_1:MS-2.7-008" in finding.taxonomy_refs
