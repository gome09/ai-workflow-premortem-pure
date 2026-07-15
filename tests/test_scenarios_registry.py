from __future__ import annotations

from scenarios import get_scenario, list_scenarios, read_scenario_input


def test_builtin_scenarios_are_enumerable():
    items = list_scenarios()
    scenario_ids = {item.scenario_id for item in items}
    assert "generic_rag_demo" in scenario_ids
    assert "university_mental_health" in scenario_ids


def test_builtin_scenario_can_be_loaded_with_input():
    scenario = get_scenario("university_mental_health")
    assert scenario.domain_profile == "university_ai"
    assert scenario.mock_fixture == "university_mental_health"
    content = read_scenario_input("university_mental_health")
    assert "心理健康风险预测" in content
    assert "应用场景" in content
