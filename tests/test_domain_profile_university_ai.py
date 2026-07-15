# tests/test_domain_profile_university_ai.py
"""
Deterministic tests for the university_ai domain profile.

Coverage:
  - Prompt dispatchers (get_stage_prompts, get_json_prompts)
  - Risk description extension (get_risk_descriptions)
  - Taxonomy ref extension (refs_for_risk_type_extended, controls_for_risk_type_extended)
  - Example input files presence and required fields
  - Stage executor build_system_prompt with profile patching (no live LLM)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

# ── Prompt dispatchers ────────────────────────────────────────────────────────


class TestGetStagePrompts:
    def test_default_returns_existing_stage1_by_identity(self):
        from stages.prompts import STAGE_1_SYSTEM, get_stage_prompts

        prompts = get_stage_prompts("default")
        assert prompts["stage_1"] is STAGE_1_SYSTEM

    def test_default_returns_existing_stage2_by_identity(self):
        from stages.prompts import STAGE_2_SYSTEM, get_stage_prompts

        prompts = get_stage_prompts("default")
        assert prompts["stage_2"] is STAGE_2_SYSTEM

    def test_default_returns_existing_init_by_identity(self):
        from stages.prompts import INIT_SYSTEM, get_stage_prompts

        prompts = get_stage_prompts("default")
        assert prompts["init"] is INIT_SYSTEM

    def test_default_returns_existing_review_prompts_by_identity(self):
        from stages.prompts import REVIEW_PROMPTS, get_stage_prompts

        prompts = get_stage_prompts("default")
        assert prompts["review"] is REVIEW_PROMPTS

    def test_university_ai_stage1_is_different_object(self):
        from stages.prompts import STAGE_1_SYSTEM, get_stage_prompts

        prompts = get_stage_prompts("university_ai")
        assert prompts["stage_1"] is not STAGE_1_SYSTEM

    def test_university_ai_stage1_contains_university_keyword(self):
        from stages.prompts import get_stage_prompts

        prompts = get_stage_prompts("university_ai")
        assert "高校" in prompts["stage_1"]

    def test_university_ai_init_mentions_data_collection(self):
        from stages.prompts import get_stage_prompts

        prompts = get_stage_prompts("university_ai")
        assert "数据" in prompts["init"]

    def test_all_six_keys_present_for_default(self):
        from stages.prompts import get_stage_prompts

        prompts = get_stage_prompts("default")
        for key in ("stage_1", "stage_2", "stage_3", "stage_4", "init", "review"):
            assert key in prompts, f"default missing key '{key}'"

    def test_all_six_keys_present_for_university_ai(self):
        from stages.prompts import get_stage_prompts

        prompts = get_stage_prompts("university_ai")
        for key in ("stage_1", "stage_2", "stage_3", "stage_4", "init", "review"):
            assert key in prompts, f"university_ai missing key '{key}'"

    def test_unknown_profile_falls_back_to_default(self):
        from stages.prompts import STAGE_1_SYSTEM, get_stage_prompts

        prompts = get_stage_prompts("nonexistent_profile_xyz")
        assert prompts["stage_1"] is STAGE_1_SYSTEM

    def test_university_ai_review_prompts_has_all_four_stages(self):
        from stages.prompts import get_stage_prompts

        review = get_stage_prompts("university_ai")["review"]
        assert isinstance(review, dict)
        for stage in (1, 2, 3, 4):
            assert stage in review, f"university_ai REVIEW_PROMPTS missing stage {stage}"


class TestGetJsonPrompts:
    def test_default_returns_existing_stage1_by_identity(self):
        from stages.json_prompts import STAGE_1_JSON_SYSTEM, get_json_prompts

        prompts = get_json_prompts("default")
        assert prompts["stage_1"] is STAGE_1_JSON_SYSTEM

    def test_university_ai_stage1_is_different_object(self):
        from stages.json_prompts import STAGE_1_JSON_SYSTEM, get_json_prompts

        prompts = get_json_prompts("university_ai")
        assert prompts["stage_1"] is not STAGE_1_JSON_SYSTEM

    def test_university_ai_stage3_contains_test_case_schema(self):
        from stages.json_prompts import get_json_prompts

        prompts = get_json_prompts("university_ai")
        assert "test_cases" in prompts["stage_3"]

    def test_all_four_keys_present_for_default(self):
        from stages.json_prompts import get_json_prompts

        prompts = get_json_prompts("default")
        for key in ("stage_1", "stage_2", "stage_3", "stage_4"):
            assert key in prompts

    def test_all_four_keys_present_for_university_ai(self):
        from stages.json_prompts import get_json_prompts

        prompts = get_json_prompts("university_ai")
        for key in ("stage_1", "stage_2", "stage_3", "stage_4"):
            assert key in prompts

    def test_unknown_profile_falls_back_to_default(self):
        from stages.json_prompts import STAGE_1_JSON_SYSTEM, get_json_prompts

        prompts = get_json_prompts("nonexistent_profile_xyz")
        assert prompts["stage_1"] is STAGE_1_JSON_SYSTEM


# ── Risk description extension ────────────────────────────────────────────────


class TestGetRiskDescriptions:
    def test_default_returns_exact_base_keys(self):
        from tools.risk_taxonomy import RISK_DESCRIPTIONS, get_risk_descriptions

        result = get_risk_descriptions("default")
        assert set(result.keys()) == set(RISK_DESCRIPTIONS.keys())

    def test_default_values_match_base_values(self):
        from tools.risk_taxonomy import RISK_DESCRIPTIONS, get_risk_descriptions

        result = get_risk_descriptions("default")
        for key, val in RISK_DESCRIPTIONS.items():
            assert result[key] == val

    def test_university_ai_adds_student_data_privacy(self):
        from tools.risk_taxonomy import get_risk_descriptions

        result = get_risk_descriptions("university_ai")
        assert "student_data_privacy" in result

    def test_university_ai_adds_academic_integrity(self):
        from tools.risk_taxonomy import get_risk_descriptions

        result = get_risk_descriptions("university_ai")
        assert "academic_integrity" in result

    def test_university_ai_adds_model_bias_edu(self):
        from tools.risk_taxonomy import get_risk_descriptions

        result = get_risk_descriptions("university_ai")
        assert "model_bias_edu" in result

    def test_university_ai_adds_irb_noncompliance(self):
        from tools.risk_taxonomy import get_risk_descriptions

        result = get_risk_descriptions("university_ai")
        assert "irb_noncompliance" in result

    def test_university_ai_adds_data_governance_gap(self):
        from tools.risk_taxonomy import get_risk_descriptions

        result = get_risk_descriptions("university_ai")
        assert "data_governance_gap" in result

    def test_university_ai_adds_over_reliance_edu(self):
        from tools.risk_taxonomy import get_risk_descriptions

        result = get_risk_descriptions("university_ai")
        assert "over_reliance_edu" in result

    def test_university_ai_preserves_all_base_types(self):
        from tools.risk_taxonomy import RISK_DESCRIPTIONS, get_risk_descriptions

        result = get_risk_descriptions("university_ai")
        for key in RISK_DESCRIPTIONS:
            assert key in result

    def test_university_ai_has_thirteen_types(self):
        from tools.risk_taxonomy import get_risk_descriptions

        result = get_risk_descriptions("university_ai")
        assert len(result) == 16  # 10 base + 6 new

    def test_unknown_profile_returns_base_only(self):
        from tools.risk_taxonomy import RISK_DESCRIPTIONS, get_risk_descriptions

        result = get_risk_descriptions("unknown_profile_xyz")
        assert set(result.keys()) == set(RISK_DESCRIPTIONS.keys())


# ── Taxonomy ref extension ────────────────────────────────────────────────────


class TestRefsForRiskTypeExtended:
    def test_default_equals_standard_for_prompt_injection(self):
        from tools.taxonomies.mapper import refs_for_risk_type, refs_for_risk_type_extended

        assert refs_for_risk_type_extended("prompt_injection", "default") == refs_for_risk_type(
            "prompt_injection"
        )

    def test_default_equals_standard_for_sensitive_info(self):
        from tools.taxonomies.mapper import refs_for_risk_type, refs_for_risk_type_extended

        assert refs_for_risk_type_extended("sensitive_info", "default") == refs_for_risk_type(
            "sensitive_info"
        )

    def test_default_equals_standard_for_policy_gap(self):
        from tools.taxonomies.mapper import refs_for_risk_type, refs_for_risk_type_extended

        assert refs_for_risk_type_extended("policy_gap", "default") == refs_for_risk_type(
            "policy_gap"
        )

    def test_student_data_privacy_returns_pipl_ref_for_university(self):
        from tools.taxonomies.mapper import refs_for_risk_type_extended

        refs = refs_for_risk_type_extended("student_data_privacy", "university_ai")
        assert len(refs) > 0
        assert any("PIPL" in ref for ref in refs)

    def test_academic_integrity_returns_refs_for_university(self):
        from tools.taxonomies.mapper import refs_for_risk_type_extended

        refs = refs_for_risk_type_extended("academic_integrity", "university_ai")
        assert len(refs) > 0

    def test_model_bias_edu_returns_refs_for_university(self):
        from tools.taxonomies.mapper import refs_for_risk_type_extended

        refs = refs_for_risk_type_extended("model_bias_edu", "university_ai")
        assert len(refs) > 0
        assert any("UNESCO" in ref or "NIST" in ref for ref in refs)

    def test_standard_risk_type_still_gets_owasp_refs_under_university_profile(self):
        from tools.taxonomies.mapper import refs_for_risk_type_extended

        refs = refs_for_risk_type_extended("prompt_injection", "university_ai")
        assert any("OWASP" in ref for ref in refs)

    def test_student_data_privacy_returns_empty_for_default_profile(self):
        from tools.taxonomies.mapper import refs_for_risk_type_extended

        refs = refs_for_risk_type_extended("student_data_privacy", "default")
        assert refs == []

    def test_none_risk_type_returns_empty(self):
        from tools.taxonomies.mapper import refs_for_risk_type_extended

        assert refs_for_risk_type_extended(None, "university_ai") == []
        assert refs_for_risk_type_extended(None, "default") == []


class TestControlsForRiskTypeExtended:
    def test_default_equals_standard_for_prompt_injection(self):
        from tools.taxonomies.mapper import controls_for_risk_type, controls_for_risk_type_extended

        assert controls_for_risk_type_extended(
            "prompt_injection", "default"
        ) == controls_for_risk_type("prompt_injection")

    def test_student_data_privacy_returns_controls_for_university(self):
        from tools.taxonomies.mapper import controls_for_risk_type_extended

        controls = controls_for_risk_type_extended("student_data_privacy", "university_ai")
        assert len(controls) > 0
        assert any("DATA_MINIMIZATION" in c for c in controls)


# ── Example files ─────────────────────────────────────────────────────────────


class TestExampleFiles:
    def test_mental_health_example_exists(self):
        p = Path("examples/university_ai_mental_health_input.md")
        assert p.exists(), f"{p} not found"

    def test_mental_health_example_is_non_empty(self):
        p = Path("examples/university_ai_mental_health_input.md")
        assert p.stat().st_size > 100

    def test_mental_health_contains_all_required_fields(self):
        content = Path("examples/university_ai_mental_health_input.md").read_text(encoding="utf-8")
        for field in ("系统名称", "应用场景", "核心目标", "涉及数据"):
            assert field in content, f"mental_health missing field '{field}'"

    def test_mental_health_mentions_prediction_and_students(self):
        content = Path("examples/university_ai_mental_health_input.md").read_text(encoding="utf-8")
        assert "心理" in content
        assert "学生" in content

    def test_mental_health_mentions_high_risk_scenario(self):
        content = Path("examples/university_ai_mental_health_input.md").read_text(encoding="utf-8")
        assert "预警" in content or "风险" in content


# ── Stage executor profile routing (no live LLM) ─────────────────────────────


class TestStageExecutorProfileRouting:
    def test_stage1_default_profile_produces_generic_prompt(self, base_ctx):
        from stages.stage_1_failure_mode import Stage1Executor

        executor = Stage1Executor()
        with patch("stages.stage_1_failure_mode.settings") as ms:
            ms.stage_output_mode = "json_first"
            ms.domain_profile = "default"
            with patch.object(executor, "_prepare_materials", return_value="[资料]"):
                prompt = executor.build_system_prompt(base_ctx)
        assert "失败模式" in prompt
        assert "高校" not in prompt

    def test_stage1_university_ai_profile_produces_university_prompt(self, base_ctx):
        from stages.stage_1_failure_mode import Stage1Executor

        executor = Stage1Executor()
        with patch("stages.stage_1_failure_mode.settings") as ms:
            ms.stage_output_mode = "json_first"
            ms.domain_profile = "university_ai"
            with patch.object(executor, "_prepare_materials", return_value="[资料]"):
                prompt = executor.build_system_prompt(base_ctx)
        assert "高校" in prompt or "学生" in prompt

    def test_stage4_default_profile_produces_generic_prompt(self, base_ctx):
        from stages.stage_4_trigger import Stage4Executor

        executor = Stage4Executor()
        with patch("stages.stage_4_trigger.settings") as ms:
            ms.stage_output_mode = "json_first"
            ms.domain_profile = "default"
            prompt = executor.build_system_prompt(base_ctx)
        assert "触发" in prompt or "工具" in prompt or "trigger" in prompt.lower()

    def test_stage4_university_ai_produces_university_prompt(self, base_ctx):
        from stages.stage_4_trigger import Stage4Executor

        executor = Stage4Executor()
        with patch("stages.stage_4_trigger.settings") as ms:
            ms.stage_output_mode = "json_first"
            ms.domain_profile = "university_ai"
            prompt = executor.build_system_prompt(base_ctx)
        assert "责任主体" in prompt or "操作步骤" in prompt or "执行" in prompt

    def test_stage1_markdown_mode_default_profile(self, base_ctx):
        from stages.stage_1_failure_mode import Stage1Executor

        executor = Stage1Executor()
        with patch("stages.stage_1_failure_mode.settings") as ms:
            ms.stage_output_mode = "markdown_legacy"
            ms.domain_profile = "default"
            with patch.object(executor, "_prepare_materials", return_value="[资料]"):
                prompt = executor.build_system_prompt(base_ctx)
        assert "失败模式" in prompt

    def test_stage1_markdown_mode_university_ai_profile(self, base_ctx):
        from stages.stage_1_failure_mode import Stage1Executor

        executor = Stage1Executor()
        with patch("stages.stage_1_failure_mode.settings") as ms:
            ms.stage_output_mode = "markdown_legacy"
            ms.domain_profile = "university_ai"
            with patch.object(executor, "_prepare_materials", return_value="[资料]"):
                prompt = executor.build_system_prompt(base_ctx)
        assert "高校" in prompt or "学生" in prompt
