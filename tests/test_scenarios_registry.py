from __future__ import annotations

from scenarios import get_scenario, list_scenarios, read_scenario_input


def test_builtin_scenarios_are_enumerable():
    items = list_scenarios()
    scenario_ids = {item.scenario_id for item in items}
    assert "generic_rag_demo" in scenario_ids
    assert "university_course_qa" in scenario_ids
    assert "university_mental_health" in scenario_ids
    expected_names = {
        "generic_rag_demo": "通用 RAG 知识库问答",
        "university_course_qa": "高校课程知识问答",
        "university_mental_health": "高校学生心理健康风险预测",
        "student_course_selection": "学生选课管理系统",
    }
    assert {item.scenario_id: item.name for item in items} == expected_names


def test_builtin_scenario_can_be_loaded_with_input():
    scenario = get_scenario("university_course_qa")
    assert scenario.domain_profile == "university_ai"
    assert scenario.mock_fixture == "university_ai"
    content = read_scenario_input("university_course_qa")
    assert "课程知识问答助手" in content
    assert "应用场景" in content
