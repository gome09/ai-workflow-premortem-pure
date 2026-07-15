"""T2.2 NIST AI 600-1 Generative AI Profile 动作项标签表测试。

注意：本测试只 import nist_ai_600_1.py，不 import mapper.py。
聚合接入测试在 Wave 2 阶段补充。
"""

from tools.taxonomies.nist_ai_600_1 import (
    NIST_GAI_ACTION_DESCRIPTIONS,
    NIST_GAI_ACTION_REFS,
)

# 10 个 risk_type 必须全部覆盖（含 T2.1 新增的 3 个）
EXPECTED_RISK_TYPES = {
    "prompt_injection",
    "sensitive_info",
    "unsupported_claim",
    "over_autonomy",
    "unsafe_instruction",
    "source_untrusted",
    "policy_gap",
    "improper_output_handling",
    "system_prompt_leakage",
    "unbounded_consumption",
}


def test_nist_gai_action_refs_covers_all_risk_types():
    """所有 10 个 risk_type 都必须有 NIST AI 600-1 动作项映射。"""
    missing = EXPECTED_RISK_TYPES - set(NIST_GAI_ACTION_REFS.keys())
    assert not missing, f"NIST_GAI_ACTION_REFS 缺失 risk_type: {missing}"


def test_nist_gai_action_refs_format():
    """所有 ref 必须形如 NIST_AI_600_1:<FUNC>-<CAT>-<NUM>。"""
    import re

    pattern = re.compile(r"^NIST_AI_600_1:(GV|MS|MP|MN)-\d+\.\d+-\d+$")
    for risk_type, refs in NIST_GAI_ACTION_REFS.items():
        for ref in refs:
            assert pattern.match(ref), (
                f"risk_type={risk_type} 的 ref={ref} 不符合 NIST_AI_600_1:<FUNC>-<CAT>-<NUM> 格式"
            )


def test_action_descriptions_covers_all_referenced_ids():
    """所有被引用的动作项编号在 NIST_GAI_ACTION_DESCRIPTIONS 都有摘要条目。"""
    referenced_ids = set()
    for refs in NIST_GAI_ACTION_REFS.values():
        for ref in refs:
            # 提取 MS-2.7-008 部分
            action_id = ref.split(":", 1)[1] if ":" in ref else ref
            referenced_ids.add(action_id)

    missing = referenced_ids - set(NIST_GAI_ACTION_DESCRIPTIONS.keys())
    assert not missing, f"以下动作项编号缺摘要: {missing}"


def test_action_descriptions_have_zh_and_source():
    """每个动作项摘要必须有 zh 和 source 字段。"""
    for action_id, desc in NIST_GAI_ACTION_DESCRIPTIONS.items():
        assert "zh" in desc, f"{action_id} 缺 zh 字段"
        assert "source" in desc, f"{action_id} 缺 source 字段"
        assert desc["zh"], f"{action_id} 的 zh 为空"
        assert desc["source"], f"{action_id} 的 source 为空"


def test_at_least_6_action_items():
    """至少有 6 个动作项（设计方案基线）。"""
    assert len(NIST_GAI_ACTION_DESCRIPTIONS) >= 6, (
        f"动作项数 {len(NIST_GAI_ACTION_DESCRIPTIONS)} < 6"
    )


def test_no_empty_refs():
    """任何 risk_type 的 refs 列表不能为空。"""
    for risk_type, refs in NIST_GAI_ACTION_REFS.items():
        assert refs, f"risk_type={risk_type} 的 refs 为空列表"
