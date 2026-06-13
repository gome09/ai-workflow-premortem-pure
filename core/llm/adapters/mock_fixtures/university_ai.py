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
                    "category": "Academic Integrity Risk",
                    "description": "AI system may enable or facilitate academic dishonesty by generating complete assignment solutions without disclosure",
                    "severity": "high",
                    "evidence": "Mock response — demo mode",
                    "evidence_ids": ["EVID-MOCK-001"],
                    "mitigation_hint": "Implement disclosure requirements and output watermarking for AI-assisted submissions",
                    "requires_human_review": True,
                },
                {
                    "id": "FM-UNIV-002",
                    "category": "Pedagogical Effectiveness Gap",
                    "description": "Over-reliance on AI tutoring may reduce deep learning and critical thinking skill development in students",
                    "severity": "medium",
                    "evidence": "Mock response — demo mode",
                    "evidence_ids": ["EVID-MOCK-002"],
                    "mitigation_hint": "Design scaffolded AI assistance that guides rather than replaces student reasoning",
                    "requires_human_review": False,
                },
            ],
            "direct_conclusion": "Mock response — demo mode. University AI deployment poses academic integrity risks (high) and pedagogical effectiveness gaps (medium). Institutional policy and human oversight mechanisms are required.",
            "open_questions": [
                "What are the institutional policies on AI tool disclosure?",
                "How will student learning outcomes be monitored over time?",
            ],
        }
    )


def stage_2_response() -> str:
    return json.dumps(
        {
            "workflow_nodes": [
                {
                    "node_id": "NODE-UNIV-001",
                    "stage_name": "Academic Integrity Screening",
                    "model_assigned": "mock-model",
                    "human_action": "Faculty review of AI-assisted submissions for compliance with academic integrity policy",
                    "check_criteria": [
                        "Student has disclosed AI assistance in submission",
                        "AI contribution does not exceed permitted thresholds",
                    ],
                    "addressed_failure_mode_ids": ["FM-UNIV-001"],
                    "prompt_template": "Assess the following submission for academic integrity compliance: {submission}",
                    "human_review_required": True,
                    "oversight_risk_level": "high",
                    "evidence_required": True,
                    "can_auto_continue": False,
                },
                {
                    "node_id": "NODE-UNIV-002",
                    "stage_name": "Learning Outcome Monitoring",
                    "model_assigned": "mock-model",
                    "human_action": "Educator review of student engagement and comprehension metrics",
                    "check_criteria": [
                        "Student demonstrates understanding beyond AI-generated content",
                        "Learning trajectory shows appropriate skill development",
                    ],
                    "addressed_failure_mode_ids": ["FM-UNIV-002"],
                    "prompt_template": "Evaluate learning progress for: {student_context}",
                    "human_review_required": False,
                    "oversight_risk_level": "medium",
                    "evidence_required": False,
                    "can_auto_continue": True,
                },
            ],
            "design_rationale": "Mock response — demo mode. Two-node workflow addressing academic integrity screening and learning outcome monitoring for university AI deployment.",
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
                    "test_input": "Student submission with disclosed AI assistance for essay outline generation",
                    "expected_behavior": "System flags for faculty review and records disclosure metadata",
                    "predicted_failure": None,
                    "correction_prompt": None,
                    "pass_criteria": [
                        "Disclosure is correctly recorded",
                        "Faculty review notification is triggered",
                    ],
                    "passed": True,
                },
                {
                    "case_id": "TC-UNIV-002",
                    "target_node_id": "NODE-UNIV-001",
                    "scenario_type": "adversarial",
                    "test_input": "Student submission using AI without disclosure, attempting to evade detection",
                    "expected_behavior": "System detects undisclosed AI usage patterns and escalates to faculty review",
                    "predicted_failure": "Sophisticated obfuscation may evade AI detection heuristics",
                    "correction_prompt": "Augment detection with stylometric analysis and cross-submission comparison",
                    "pass_criteria": [
                        "Undisclosed AI usage is flagged with appropriate confidence level",
                        "False positive rate remains below 5%",
                    ],
                    "passed": True,
                },
            ],
            "overall_passed": True,
            "risk_summary": "Mock response — demo mode. Academic integrity screening passed for standard and adversarial scenarios in university AI context.",
        }
    )


def stage_4_response() -> str:
    return json.dumps(
        {
            "trigger_methods": [
                {
                    "node_id": "NODE-UNIV-001",
                    "model_or_mode": "mock-model",
                    "entry_point": "POST /api/v1/university/integrity-check",
                    "trigger_instruction": "Submit student work with metadata (student_id, course_id, assignment_id, disclosure_flag) as JSON payload.",
                    "execution_suggestion": "Integrate with LMS submission webhook for automatic triggering. Maintain audit log for accreditation purposes.",
                    "human_review_required": True,
                },
                {
                    "node_id": "NODE-UNIV-002",
                    "model_or_mode": "mock-model",
                    "entry_point": "POST /api/v1/university/learning-monitor",
                    "trigger_instruction": "Submit aggregated learning metrics (engagement_score, comprehension_score, ai_usage_ratio) per student per course.",
                    "execution_suggestion": "Schedule weekly batch runs. Alert educators when learning trajectory deviates significantly from baseline.",
                    "human_review_required": False,
                },
            ],
            "final_notes": "Mock response — demo mode. University AI workflow integrates with institutional LMS. Human review mandatory for integrity gate; learning monitoring runs automatically.",
        }
    )
