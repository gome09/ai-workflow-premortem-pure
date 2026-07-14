"""T2.4 TC260 智能体部署使用安全指引标签表测试。

注意：本测试只 import tc260_agent_deployment.py，不 import mapper.py。
聚合接入测试在 Wave 2 阶段补充。
"""

from tools.taxonomies.tc260_agent_deployment import (
    TC260_CONTROL_REFS,
    TC260_RISK_REFS,
    TC260_STAGE_MAP,
)

EXPECTED_STAGES = {"评估", "准备", "部署", "使用", "停用"}


def test_tc260_stage_map_has_five_stages():
    """TC260_STAGE_MAP 必须含 5 个阶段 key。"""
    assert set(TC260_STAGE_MAP.keys()) == EXPECTED_STAGES


def test_tc260_stage_map_decommission_is_none():
    """产品缺口测试：停用阶段无对应能力，必须为 None。"""
    assert TC260_STAGE_MAP["停用"] is None, (
        "TC260_STAGE_MAP['停用'] 必须为 None（产品缺口，本项目无停用阶段）"
    )


def test_tc260_stage_map_other_stages_mapped():
    """评估/准备/部署/使用 4 个阶段必须映射到本项目 stage。"""
    for stage in ["评估", "准备", "部署", "使用"]:
        assert TC260_STAGE_MAP[stage] is not None, f"{stage} 不应为 None"
        assert TC260_STAGE_MAP[stage].startswith("stage_"), (
            f"{stage} 映射值 {TC260_STAGE_MAP[stage]} 不以 stage_ 开头"
        )


def test_tc260_control_refs_format():
    """所有 TC260_CONTROL_REFS 的 ref 必须以 TC260_AGENT: 开头。"""
    for control_key, refs in TC260_CONTROL_REFS.items():
        for ref in refs:
            assert ref.startswith("TC260_AGENT:"), (
                f"control_key={control_key} 的 ref={ref} 不以 TC260_AGENT: 开头"
            )


def test_tc260_risk_refs_format():
    """所有 TC260_RISK_REFS 的 ref 必须以 TC260_AGENT: 开头。"""
    for risk_type, refs in TC260_RISK_REFS.items():
        for ref in refs:
            assert ref.startswith("TC260_AGENT:"), (
                f"risk_type={risk_type} 的 ref={ref} 不以 TC260_AGENT: 开头"
            )


def test_tc260_risk_refs_covers_over_autonomy():
    """over_autonomy 映射到 MIN_PRIVILEGE + HUMAN_OVERSIGHT。"""
    refs = TC260_RISK_REFS.get("over_autonomy", [])
    assert "TC260_AGENT:MIN_PRIVILEGE" in refs
    assert "TC260_AGENT:HUMAN_OVERSIGHT" in refs


def test_tc260_risk_refs_covers_unbounded_consumption():
    """LLM10 衍生 risk_type 也应有 TC260 映射。"""
    refs = TC260_RISK_REFS.get("unbounded_consumption", [])
    assert "TC260_AGENT:RESOURCE_LIMIT" in refs


def test_tc260_risk_refs_covers_system_prompt_leakage():
    """LLM07 衍生 risk_type 也应有 TC260 映射。"""
    refs = TC260_RISK_REFS.get("system_prompt_leakage", [])
    assert "TC260_AGENT:SENSITIVE_DATA_MINIMAL" in refs


def test_tc260_risk_refs_not_empty():
    """任何映射的 refs 列表不能为空。"""
    for k, refs in TC260_RISK_REFS.items():
        assert refs, f"TC260_RISK_REFS[{k}] 为空"


def test_tc260_control_refs_covers_key_controls():
    """关键 control 必须存在。"""
    expected_controls = {
        "min_privilege",
        "directory_access_limit",
        "sensitive_data_minimal",
        "human_oversight",
        "resource_limit",
        "audit_log",
    }
    missing = expected_controls - set(TC260_CONTROL_REFS.keys())
    assert not missing, f"TC260_CONTROL_REFS 缺失: {missing}"
