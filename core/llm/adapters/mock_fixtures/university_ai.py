# core/llm/adapters/mock_fixtures/university_ai.py
"""Stage fixture responses for the university_ai domain profile (demo/offline mode)."""

from __future__ import annotations

import json


def stage_1_response() -> str:
    return json.dumps(
        {
            "failure_modes": [
                {
                    "id": "FM-UNIV-001",
                    "category": "学术诚信风险",
                    "description": "AI 系统在未标注的情况下直接生成完整作业答案，可能助长学术不端行为",
                    "severity": "high",
                    "evidence": "演示数据 — 未连接真实模型",
                    "evidence_ids": ["EVID-MOCK-001"],
                    "mitigation_hint": "对 AI 辅助完成的提交要求强制披露，并对输出加水印标识",
                    "requires_human_review": True,
                },
                {
                    "id": "FM-UNIV-002",
                    "category": "教学有效性缺口",
                    "description": "过度依赖 AI 辅导可能削弱学生深度学习与批判性思维能力的培养",
                    "severity": "medium",
                    "evidence": "演示数据 — 未连接真实模型",
                    "evidence_ids": ["EVID-MOCK-002"],
                    "mitigation_hint": "设计引导式 AI 辅助方案，启发而非替代学生的独立思考",
                    "requires_human_review": False,
                },
            ],
            "direct_conclusion": "演示数据（未连接真实模型）。高校 AI 应用存在学术诚信风险（高）与教学有效性缺口（中），需要配套制度与人工监督机制。",
            "open_questions": [
                "学校对 AI 工具使用披露有哪些既定政策？",
                "学生学习成效将如何持续追踪？",
            ],
        }
    )


def stage_2_response() -> str:
    return json.dumps(
        {
            "workflow_nodes": [
                {
                    "node_id": "NODE-UNIV-001",
                    "stage_name": "学术诚信审查关卡",
                    "model_assigned": "演示模型",
                    "human_action": "教师审核 AI 辅助提交的作业是否符合学术诚信政策",
                    "check_criteria": [
                        "学生已在提交材料中披露 AI 辅助情况",
                        "AI 贡献比例未超出允许阈值",
                    ],
                    "addressed_failure_mode_ids": ["FM-UNIV-001"],
                    "prompt_template": "请评估以下提交材料是否符合学术诚信要求：{submission}",
                    "human_review_required": True,
                    "oversight_risk_level": "high",
                    "evidence_required": True,
                    "can_auto_continue": False,
                },
                {
                    "node_id": "NODE-UNIV-002",
                    "stage_name": "学习成效跟踪",
                    "model_assigned": "演示模型",
                    "human_action": "教育者审核学生参与度与理解程度指标",
                    "check_criteria": [
                        "学生表现出超出 AI 生成内容的理解能力",
                        "学习轨迹显示出合理的能力发展",
                    ],
                    "addressed_failure_mode_ids": ["FM-UNIV-002"],
                    "prompt_template": "请评估以下学生的学习进展：{student_context}",
                    "human_review_required": False,
                    "oversight_risk_level": "medium",
                    "evidence_required": False,
                    "can_auto_continue": True,
                },
            ],
            "design_rationale": "演示数据（未连接真实模型）。采用学术诚信审查 + 学习成效跟踪两个节点，覆盖高校 AI 应用的两个失败模式。",
            "open_questions": [],
        }
    )


def stage_3_response() -> str:
    return json.dumps(
        {
            "test_cases": [
                {
                    "case_id": "TC-UNIV-001",
                    "target_node_id": "NODE-UNIV-001",
                    "scenario_type": "normal",
                    "test_input": "学生提交作业时已披露使用 AI 辅助生成论文大纲",
                    "expected_behavior": "系统标记该提交待教师审核，并记录披露信息",
                    "predicted_failure": None,
                    "correction_prompt": None,
                    "pass_criteria": [
                        "披露信息被正确记录",
                        "触发教师审核通知",
                    ],
                    "passed": True,
                },
                {
                    "case_id": "TC-UNIV-002",
                    "target_node_id": "NODE-UNIV-001",
                    "scenario_type": "adversarial",
                    "test_input": "学生使用 AI 但未披露，并尝试规避检测",
                    "expected_behavior": "系统检测到未披露的 AI 使用痕迹并上报教师审核",
                    "predicted_failure": "较复杂的规避手段可能绕过 AI 检测启发式规则",
                    "correction_prompt": "结合文体分析与跨提交比对，增强检测能力",
                    "pass_criteria": [
                        "未披露的 AI 使用以合理置信度被标记",
                        "误报率控制在 5% 以下",
                    ],
                    "passed": True,
                },
            ],
            "overall_passed": True,
            "risk_summary": "演示数据（未连接真实模型）。学术诚信审查在常规与对抗性场景下均通过测试。",
        }
    )


def stage_4_response() -> str:
    return json.dumps(
        {
            "trigger_methods": [
                {
                    "node_id": "NODE-UNIV-001",
                    "model_or_mode": "演示模型",
                    "entry_point": "POST /api/v1/university/integrity-check",
                    "trigger_instruction": "提交包含学生作业及元数据（student_id、course_id、assignment_id、disclosure_flag）的 JSON 请求体。",
                    "execution_suggestion": "与教学管理系统（LMS）提交 webhook 集成以自动触发，并保留审计日志用于认证评估。",
                    "human_review_required": True,
                },
                {
                    "node_id": "NODE-UNIV-002",
                    "model_or_mode": "演示模型",
                    "entry_point": "POST /api/v1/university/learning-monitor",
                    "trigger_instruction": "按学生、按课程提交聚合学习指标（engagement_score、comprehension_score、ai_usage_ratio）。",
                    "execution_suggestion": "安排每周批处理运行，当学习轨迹明显偏离基线时提醒教育者。",
                    "human_review_required": False,
                },
            ],
            "final_notes": "演示数据（未连接真实模型）。高校 AI 工作流与校内教学系统集成；诚信审查关卡强制人工复核，学习跟踪自动运行。",
        }
    )
