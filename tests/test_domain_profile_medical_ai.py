# tests/test_domain_profile_medical_ai.py
"""
Deterministic tests for the medical_ai domain profile.

Coverage:
  - Prompt dispatchers (get_stage_prompts, get_json_prompts)
  - Risk description extension (get_risk_descriptions)
  - Taxonomy ref extension (refs_for_risk_type_extended, controls_for_risk_type_extended)
  - Profile isolation (default behaviour unchanged)
  - Stage executor build_system_prompt with profile patching (no live LLM)
"""

from __future__ import annotations

from unittest.mock import patch

# ── Prompt dispatchers ────────────────────────────────────────────────────────


class TestGetStagePromptsMedicalAi:
    def test_medical_ai_returns_all_six_keys(self):
        from stages.prompts import get_stage_prompts

        prompts = get_stage_prompts("medical_ai")
        for key in ("stage_1", "stage_2", "stage_3", "stage_4", "init", "review"):
            assert key in prompts, f"medical_ai missing key '{key}'"

    def test_medical_ai_stage1_is_different_from_default(self):
        from stages.prompts import STAGE_1_SYSTEM, get_stage_prompts

        prompts = get_stage_prompts("medical_ai")
        assert prompts["stage_1"] is not STAGE_1_SYSTEM

    def test_medical_ai_stage1_contains_medical_keyword(self):
        from stages.prompts import get_stage_prompts

        prompts = get_stage_prompts("medical_ai")
        stage1 = prompts["stage_1"]
        assert any(kw in stage1 for kw in ("医疗", "患者", "诊断", "临床"))

    def test_medical_ai_stage2_contains_clinical_keyword(self):
        from stages.prompts import get_stage_prompts

        prompts = get_stage_prompts("medical_ai")
        assert any(kw in prompts["stage_2"] for kw in ("临床", "患者", "诊疗", "医院"))

    def test_medical_ai_stage3_contains_test_keyword(self):
        from stages.prompts import get_stage_prompts

        prompts = get_stage_prompts("medical_ai")
        assert any(kw in prompts["stage_3"] for kw in ("测试", "验证", "患者"))

    def test_medical_ai_stage4_contains_execution_keyword(self):
        from stages.prompts import get_stage_prompts

        prompts = get_stage_prompts("medical_ai")
        assert any(kw in prompts["stage_4"] for kw in ("执行", "操作", "步骤", "审计"))

    def test_medical_ai_init_mentions_patient_population(self):
        from stages.prompts import get_stage_prompts

        prompts = get_stage_prompts("medical_ai")
        assert any(kw in prompts["init"] for kw in ("患者", "科室", "决策"))

    def test_medical_ai_review_prompts_is_dict(self):
        from stages.prompts import get_stage_prompts

        review = get_stage_prompts("medical_ai")["review"]
        assert isinstance(review, dict)

    def test_medical_ai_review_prompts_has_all_four_stages(self):
        from stages.prompts import get_stage_prompts

        review = get_stage_prompts("medical_ai")["review"]
        for stage in (1, 2, 3, 4):
            assert stage in review, f"medical_ai REVIEW_PROMPTS missing stage {stage}"

    def test_medical_ai_review_stage1_non_empty(self):
        from stages.prompts import get_stage_prompts

        review = get_stage_prompts("medical_ai")["review"]
        assert len(review[1]) > 50

    def test_medical_ai_review_stage4_contains_compliance_checklist(self):
        from stages.prompts import get_stage_prompts

        review = get_stage_prompts("medical_ai")["review"]
        assert any(kw in review[4] for kw in ("HIPAA", "合规", "审计"))

    def test_medical_ai_is_different_object_from_university_ai(self):
        from stages.prompts import get_stage_prompts

        med = get_stage_prompts("medical_ai")
        uni = get_stage_prompts("university_ai")
        assert med["stage_1"] is not uni["stage_1"]

    def test_default_unaffected_by_medical_ai_import(self):
        from stages.prompts import STAGE_1_SYSTEM, get_stage_prompts

        _ = get_stage_prompts("medical_ai")
        default = get_stage_prompts("default")
        assert default["stage_1"] is STAGE_1_SYSTEM

    def test_unknown_profile_still_falls_back_to_default(self):
        from stages.prompts import STAGE_1_SYSTEM, get_stage_prompts

        prompts = get_stage_prompts("nonexistent_profile_xyz")
        assert prompts["stage_1"] is STAGE_1_SYSTEM

    def test_medical_ai_stage1_mentions_fda_or_hipaa(self):
        from stages.prompts import get_stage_prompts

        prompts = get_stage_prompts("medical_ai")
        assert any(kw in prompts["stage_1"] for kw in ("FDA", "HIPAA", "SaMD"))


class TestGetJsonPromptsMedicalAi:
    def test_medical_ai_returns_all_four_json_keys(self):
        from stages.json_prompts import get_json_prompts

        prompts = get_json_prompts("medical_ai")
        for key in ("stage_1", "stage_2", "stage_3", "stage_4"):
            assert key in prompts

    def test_medical_ai_stage1_json_is_different_from_default(self):
        from stages.json_prompts import STAGE_1_JSON_SYSTEM, get_json_prompts

        prompts = get_json_prompts("medical_ai")
        assert prompts["stage_1"] is not STAGE_1_JSON_SYSTEM

    def test_medical_ai_stage1_json_contains_failure_modes_schema(self):
        from stages.json_prompts import get_json_prompts

        prompts = get_json_prompts("medical_ai")
        assert "failure_modes" in prompts["stage_1"]

    def test_medical_ai_stage3_json_contains_test_cases_schema(self):
        from stages.json_prompts import get_json_prompts

        prompts = get_json_prompts("medical_ai")
        assert "test_cases" in prompts["stage_3"]

    def test_medical_ai_stage2_json_contains_workflow_nodes_schema(self):
        from stages.json_prompts import get_json_prompts

        prompts = get_json_prompts("medical_ai")
        assert "workflow_nodes" in prompts["stage_2"]

    def test_medical_ai_stage4_json_contains_trigger_methods_schema(self):
        from stages.json_prompts import get_json_prompts

        prompts = get_json_prompts("medical_ai")
        assert "trigger_methods" in prompts["stage_4"]

    def test_default_json_unaffected_after_medical_ai_import(self):
        from stages.json_prompts import STAGE_1_JSON_SYSTEM, get_json_prompts

        _ = get_json_prompts("medical_ai")
        default = get_json_prompts("default")
        assert default["stage_1"] is STAGE_1_JSON_SYSTEM

    def test_unknown_profile_json_falls_back_to_default(self):
        from stages.json_prompts import STAGE_1_JSON_SYSTEM, get_json_prompts

        prompts = get_json_prompts("nonexistent_profile_xyz")
        assert prompts["stage_1"] is STAGE_1_JSON_SYSTEM


# ── Risk description extension ────────────────────────────────────────────────


class TestGetRiskDescriptionsMedicalAi:
    def test_medical_ai_adds_misdiagnosis_risk(self):
        from tools.risk_taxonomy import get_risk_descriptions

        result = get_risk_descriptions("medical_ai")
        assert "misdiagnosis_risk" in result

    def test_medical_ai_adds_patient_data_privacy(self):
        from tools.risk_taxonomy import get_risk_descriptions

        result = get_risk_descriptions("medical_ai")
        assert "patient_data_privacy" in result

    def test_medical_ai_adds_informed_consent_gap(self):
        from tools.risk_taxonomy import get_risk_descriptions

        result = get_risk_descriptions("medical_ai")
        assert "informed_consent_gap" in result

    def test_medical_ai_adds_algorithmic_bias_medical(self):
        from tools.risk_taxonomy import get_risk_descriptions

        result = get_risk_descriptions("medical_ai")
        assert "algorithmic_bias_medical" in result

    def test_medical_ai_adds_over_reliance_clinical(self):
        from tools.risk_taxonomy import get_risk_descriptions

        result = get_risk_descriptions("medical_ai")
        assert "over_reliance_clinical" in result

    def test_medical_ai_adds_audit_trail_gap(self):
        from tools.risk_taxonomy import get_risk_descriptions

        result = get_risk_descriptions("medical_ai")
        assert "audit_trail_gap" in result

    def test_medical_ai_preserves_all_base_types(self):
        from tools.risk_taxonomy import RISK_DESCRIPTIONS, get_risk_descriptions

        result = get_risk_descriptions("medical_ai")
        for key in RISK_DESCRIPTIONS:
            assert key in result

    def test_medical_ai_has_thirteen_types(self):
        from tools.risk_taxonomy import get_risk_descriptions

        result = get_risk_descriptions("medical_ai")
        assert len(result) == 13  # 7 base + 6 new

    def test_medical_ai_misdiagnosis_description_is_non_empty(self):
        from tools.risk_taxonomy import get_risk_descriptions

        result = get_risk_descriptions("medical_ai")
        assert len(result["misdiagnosis_risk"]) > 10

    def test_medical_ai_patient_data_privacy_mentions_hipaa(self):
        from tools.risk_taxonomy import get_risk_descriptions

        result = get_risk_descriptions("medical_ai")
        assert "HIPAA" in result["patient_data_privacy"]

    def test_default_unchanged_does_not_include_medical_types(self):
        from tools.risk_taxonomy import get_risk_descriptions

        result = get_risk_descriptions("default")
        assert "misdiagnosis_risk" not in result
        assert "patient_data_privacy" not in result
        assert "audit_trail_gap" not in result

    def test_university_ai_unchanged_does_not_include_medical_types(self):
        from tools.risk_taxonomy import get_risk_descriptions

        result = get_risk_descriptions("university_ai")
        assert "misdiagnosis_risk" not in result
        assert "patient_data_privacy" not in result

    def test_unknown_profile_returns_base_only(self):
        from tools.risk_taxonomy import RISK_DESCRIPTIONS, get_risk_descriptions

        result = get_risk_descriptions("unknown_profile_xyz")
        assert set(result.keys()) == set(RISK_DESCRIPTIONS.keys())


# ── Taxonomy ref extension ────────────────────────────────────────────────────


class TestRefsForRiskTypeExtendedMedicalAi:
    def test_misdiagnosis_risk_returns_non_empty_refs(self):
        from tools.taxonomies.mapper import refs_for_risk_type_extended

        refs = refs_for_risk_type_extended("misdiagnosis_risk", "medical_ai")
        assert len(refs) > 0

    def test_misdiagnosis_risk_contains_fda_samd(self):
        from tools.taxonomies.mapper import refs_for_risk_type_extended

        refs = refs_for_risk_type_extended("misdiagnosis_risk", "medical_ai")
        assert any("FDA" in ref for ref in refs)

    def test_patient_data_privacy_returns_non_empty_refs(self):
        from tools.taxonomies.mapper import refs_for_risk_type_extended

        refs = refs_for_risk_type_extended("patient_data_privacy", "medical_ai")
        assert len(refs) > 0

    def test_patient_data_privacy_contains_hipaa(self):
        from tools.taxonomies.mapper import refs_for_risk_type_extended

        refs = refs_for_risk_type_extended("patient_data_privacy", "medical_ai")
        assert any("HIPAA" in ref for ref in refs)

    def test_informed_consent_gap_returns_non_empty_refs(self):
        from tools.taxonomies.mapper import refs_for_risk_type_extended

        refs = refs_for_risk_type_extended("informed_consent_gap", "medical_ai")
        assert len(refs) > 0

    def test_algorithmic_bias_medical_returns_non_empty_refs(self):
        from tools.taxonomies.mapper import refs_for_risk_type_extended

        refs = refs_for_risk_type_extended("algorithmic_bias_medical", "medical_ai")
        assert len(refs) > 0

    def test_algorithmic_bias_medical_contains_nist_or_who(self):
        from tools.taxonomies.mapper import refs_for_risk_type_extended

        refs = refs_for_risk_type_extended("algorithmic_bias_medical", "medical_ai")
        assert any("NIST" in ref or "WHO" in ref for ref in refs)

    def test_over_reliance_clinical_returns_non_empty_refs(self):
        from tools.taxonomies.mapper import refs_for_risk_type_extended

        refs = refs_for_risk_type_extended("over_reliance_clinical", "medical_ai")
        assert len(refs) > 0

    def test_audit_trail_gap_returns_non_empty_refs(self):
        from tools.taxonomies.mapper import refs_for_risk_type_extended

        refs = refs_for_risk_type_extended("audit_trail_gap", "medical_ai")
        assert len(refs) > 0

    def test_audit_trail_gap_contains_hipaa_or_iec(self):
        from tools.taxonomies.mapper import refs_for_risk_type_extended

        refs = refs_for_risk_type_extended("audit_trail_gap", "medical_ai")
        assert any("HIPAA" in ref or "IEC" in ref for ref in refs)

    def test_standard_risk_type_falls_back_to_standard_registry(self):
        from tools.taxonomies.mapper import refs_for_risk_type, refs_for_risk_type_extended

        result_extended = refs_for_risk_type_extended("prompt_injection", "medical_ai")
        result_standard = refs_for_risk_type("prompt_injection")
        assert result_extended == result_standard

    def test_medical_risk_type_returns_empty_for_default_profile(self):
        from tools.taxonomies.mapper import refs_for_risk_type_extended

        refs = refs_for_risk_type_extended("misdiagnosis_risk", "default")
        assert refs == []

    def test_none_risk_type_returns_empty_for_medical_ai(self):
        from tools.taxonomies.mapper import refs_for_risk_type_extended

        assert refs_for_risk_type_extended(None, "medical_ai") == []

    def test_medical_ai_refs_do_not_affect_university_ai(self):
        from tools.taxonomies.mapper import refs_for_risk_type_extended

        refs = refs_for_risk_type_extended("misdiagnosis_risk", "university_ai")
        assert refs == []


class TestControlsForRiskTypeExtendedMedicalAi:
    def test_misdiagnosis_risk_returns_non_empty_controls(self):
        from tools.taxonomies.mapper import controls_for_risk_type_extended

        controls = controls_for_risk_type_extended("misdiagnosis_risk", "medical_ai")
        assert len(controls) > 0

    def test_patient_data_privacy_returns_non_empty_controls(self):
        from tools.taxonomies.mapper import controls_for_risk_type_extended

        controls = controls_for_risk_type_extended("patient_data_privacy", "medical_ai")
        assert len(controls) > 0

    def test_patient_data_privacy_controls_contain_hipaa(self):
        from tools.taxonomies.mapper import controls_for_risk_type_extended

        controls = controls_for_risk_type_extended("patient_data_privacy", "medical_ai")
        assert any("HIPAA" in c for c in controls)

    def test_informed_consent_gap_returns_non_empty_controls(self):
        from tools.taxonomies.mapper import controls_for_risk_type_extended

        controls = controls_for_risk_type_extended("informed_consent_gap", "medical_ai")
        assert len(controls) > 0

    def test_algorithmic_bias_medical_returns_non_empty_controls(self):
        from tools.taxonomies.mapper import controls_for_risk_type_extended

        controls = controls_for_risk_type_extended("algorithmic_bias_medical", "medical_ai")
        assert len(controls) > 0

    def test_over_reliance_clinical_returns_non_empty_controls(self):
        from tools.taxonomies.mapper import controls_for_risk_type_extended

        controls = controls_for_risk_type_extended("over_reliance_clinical", "medical_ai")
        assert len(controls) > 0

    def test_audit_trail_gap_returns_non_empty_controls(self):
        from tools.taxonomies.mapper import controls_for_risk_type_extended

        controls = controls_for_risk_type_extended("audit_trail_gap", "medical_ai")
        assert len(controls) > 0

    def test_standard_risk_type_falls_back_to_standard_controls(self):
        from tools.taxonomies.mapper import controls_for_risk_type, controls_for_risk_type_extended

        result_extended = controls_for_risk_type_extended("prompt_injection", "medical_ai")
        result_standard = controls_for_risk_type("prompt_injection")
        assert result_extended == result_standard

    def test_medical_control_type_returns_empty_for_default_profile(self):
        from tools.taxonomies.mapper import controls_for_risk_type_extended

        controls = controls_for_risk_type_extended("misdiagnosis_risk", "default")
        assert controls == []


# ── Module import sanity ──────────────────────────────────────────────────────


class TestMedicalAiModuleImports:
    def test_medical_ai_profile_module_imports_without_error(self):
        import stages.domain_profiles.medical_ai  # noqa: F401

    def test_medical_ai_clinical_taxonomy_imports_without_error(self):
        import tools.taxonomies.medical_ai_clinical  # noqa: F401

    def test_medical_ai_refs_dict_has_six_keys(self):
        from tools.taxonomies.medical_ai_clinical import MEDICAL_AI_REFS

        assert len(MEDICAL_AI_REFS) == 6

    def test_medical_ai_refs_dict_contains_all_six_risk_types(self):
        from tools.taxonomies.medical_ai_clinical import MEDICAL_AI_REFS

        expected = {
            "misdiagnosis_risk",
            "patient_data_privacy",
            "informed_consent_gap",
            "algorithmic_bias_medical",
            "over_reliance_clinical",
            "audit_trail_gap",
        }
        assert set(MEDICAL_AI_REFS.keys()) == expected

    def test_medical_risk_refs_and_control_refs_are_non_empty(self):
        from tools.taxonomies.medical_ai_clinical import MEDICAL_AI_REFS

        for risk_type, data in MEDICAL_AI_REFS.items():
            assert len(data["taxonomy_refs"]) > 0, f"{risk_type} has empty taxonomy_refs"
            assert len(data["control_refs"]) > 0, f"{risk_type} has empty control_refs"

    def test_medical_ai_stage_prompts_dict_has_correct_keys(self):
        from stages.domain_profiles.medical_ai import STAGE_PROMPTS

        for key in ("stage_1", "stage_2", "stage_3", "stage_4", "init", "review"):
            assert key in STAGE_PROMPTS, f"STAGE_PROMPTS missing key '{key}'"

    def test_medical_ai_json_stage_prompts_dict_has_correct_keys(self):
        from stages.domain_profiles.medical_ai import JSON_STAGE_PROMPTS

        for key in ("stage_1", "stage_2", "stage_3", "stage_4"):
            assert key in JSON_STAGE_PROMPTS, f"JSON_STAGE_PROMPTS missing key '{key}'"


# ── Stage executor profile routing (no live LLM) ─────────────────────────────


class TestStageExecutorMedicalAiRouting:
    def test_stage1_medical_ai_profile_produces_medical_prompt(self, base_ctx):
        from stages.stage_1_failure_mode import Stage1Executor

        executor = Stage1Executor()
        with patch("stages.stage_1_failure_mode.settings") as ms:
            ms.stage_output_mode = "json_first"
            ms.domain_profile = "medical_ai"
            with patch.object(executor, "_prepare_materials", return_value="[资料]"):
                prompt = executor.build_system_prompt(base_ctx)
        assert any(kw in prompt for kw in ("医疗", "患者", "诊断", "临床"))

    def test_stage1_default_profile_does_not_produce_medical_prompt(self, base_ctx):
        from stages.stage_1_failure_mode import Stage1Executor

        executor = Stage1Executor()
        with patch("stages.stage_1_failure_mode.settings") as ms:
            ms.stage_output_mode = "json_first"
            ms.domain_profile = "default"
            with patch.object(executor, "_prepare_materials", return_value="[资料]"):
                prompt = executor.build_system_prompt(base_ctx)
        assert "失败模式" in prompt
        assert "PHI" not in prompt

    def test_stage4_medical_ai_produces_medical_prompt(self, base_ctx):
        from stages.stage_4_trigger import Stage4Executor

        executor = Stage4Executor()
        with patch("stages.stage_4_trigger.settings") as ms:
            ms.stage_output_mode = "json_first"
            ms.domain_profile = "medical_ai"
            prompt = executor.build_system_prompt(base_ctx)
        assert any(kw in prompt for kw in ("审计", "操作", "执行", "临床", "医院"))

    def test_stage1_markdown_mode_medical_ai_profile(self, base_ctx):
        from stages.stage_1_failure_mode import Stage1Executor

        executor = Stage1Executor()
        with patch("stages.stage_1_failure_mode.settings") as ms:
            ms.stage_output_mode = "markdown_legacy"
            ms.domain_profile = "medical_ai"
            with patch.object(executor, "_prepare_materials", return_value="[资料]"):
                prompt = executor.build_system_prompt(base_ctx)
        assert any(kw in prompt for kw in ("医疗", "患者", "诊断", "临床"))
