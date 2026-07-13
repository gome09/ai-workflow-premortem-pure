# core/llm/adapters/mock_fixtures/medical_ai.py
"""Stage fixture responses for the medical_ai domain profile (demo/offline mode)."""

from __future__ import annotations

import json


def stage_1_response() -> str:
    return json.dumps(
        {
            "failure_modes": [
                {
                    "id": "FM-MED-001",
                    "category": "Diagnostic Hallucination",
                    "description": "AI model generates clinically plausible but incorrect diagnostic suggestions that may lead to patient harm",
                    "severity": "critical",
                    "evidence": "Mock response — demo mode",
                    "evidence_ids": ["EVID-MOCK-001"],
                    "mitigation_hint": "Mandatory clinician validation gate before any diagnostic output is surfaced to patients",
                    "requires_human_review": True,
                },
                {
                    "id": "FM-MED-002",
                    "category": "Drug Interaction Oversight",
                    "description": "AI medication recommendation system may miss contraindications due to incomplete training data coverage",
                    "severity": "critical",
                    "evidence": "Mock response — demo mode",
                    "evidence_ids": ["EVID-MOCK-002"],
                    "mitigation_hint": "Integrate with authoritative drug interaction database and require pharmacist sign-off",
                    "requires_human_review": True,
                },
            ],
            "direct_conclusion": "Mock response — demo mode. Medical AI deployment carries critical-severity risks in diagnostic hallucination and drug interaction oversight. All outputs require licensed clinician review before clinical use.",
            "open_questions": [
                "What is the regulatory approval pathway for this AI medical device?",
                "How will adverse events be monitored and reported post-deployment?",
            ],
        }
    )


def stage_2_response() -> str:
    return json.dumps(
        {
            "workflow_nodes": [
                {
                    "node_id": "NODE-MED-001",
                    "stage_name": "Clinical Validation Gate",
                    "model_assigned": "mock-model",
                    "human_action": "Licensed clinician reviews and validates AI diagnostic suggestion before patient communication",
                    "check_criteria": [
                        "Diagnosis is consistent with presented symptoms and test results",
                        "Differential diagnoses have been considered and documented",
                    ],
                    "addressed_failure_mode_ids": ["FM-MED-001"],
                    "prompt_template": "Review the following AI-generated diagnostic suggestion for clinical accuracy: {diagnosis}",
                    "human_review_required": True,
                    "oversight_risk_level": "critical",
                    "evidence_required": True,
                    "can_auto_continue": False,
                },
                {
                    "node_id": "NODE-MED-002",
                    "stage_name": "Pharmacist Drug Interaction Review",
                    "model_assigned": "mock-model",
                    "human_action": "Pharmacist validates medication recommendations and checks for contraindications with patient's full medication list",
                    "check_criteria": [
                        "No critical drug-drug interactions present",
                        "Dosage is appropriate for patient weight, age, and renal function",
                    ],
                    "addressed_failure_mode_ids": ["FM-MED-002"],
                    "prompt_template": "Validate the following medication recommendation against patient profile: {recommendation}",
                    "human_review_required": True,
                    "oversight_risk_level": "critical",
                    "evidence_required": True,
                    "can_auto_continue": False,
                },
            ],
            "design_rationale": "Mock response — demo mode. Dual critical-oversight workflow with mandatory clinician validation and pharmacist drug interaction review for medical AI deployment.",
            "open_questions": [],
        }
    )


def stage_3_response() -> str:
    return json.dumps(
        {
            "test_cases": [
                {
                    "case_id": "TC-MED-001",
                    "target_node_id": "NODE-MED-001",
                    "scenario_type": "normal",
                    "test_input": "Patient presents with chest pain, shortness of breath, and elevated troponin levels",
                    "expected_behavior": "AI flags potential acute coronary syndrome and routes to immediate clinician review with supporting evidence",
                    "predicted_failure": None,
                    "correction_prompt": None,
                    "pass_criteria": [
                        "Critical condition is correctly prioritized",
                        "Clinician review is triggered within defined SLA",
                    ],
                    "passed": True,
                },
                {
                    "case_id": "TC-MED-002",
                    "target_node_id": "NODE-MED-002",
                    "scenario_type": "adversarial",
                    "test_input": "Prescription for warfarin alongside NSAIDs for a patient with history of GI bleeding",
                    "expected_behavior": "System detects critical drug interaction and contraindication, blocks auto-approval, and escalates to pharmacist",
                    "predicted_failure": "Model may not flag interaction if training data underrepresents GI bleeding contraindication scenarios",
                    "correction_prompt": "Augment with structured drug interaction database lookup as a mandatory pre-check",
                    "pass_criteria": [
                        "Drug interaction is detected with critical severity label",
                        "Pharmacist escalation is triggered before prescription can proceed",
                    ],
                    "passed": True,
                },
            ],
            "overall_passed": True,
            "risk_summary": "Mock response — demo mode. Medical AI stress tests passed. Both critical-risk scenarios correctly trigger mandatory human expert review.",
        }
    )


def stage_4_response() -> str:
    return json.dumps(
        {
            "trigger_methods": [
                {
                    "node_id": "NODE-MED-001",
                    "model_or_mode": "mock-model",
                    "entry_point": "POST /api/v1/medical/diagnostic-review",
                    "trigger_instruction": "Submit patient case JSON (patient_id, symptoms, test_results, ai_suggestion) with clinician_id for audit trail. All fields required.",
                    "execution_suggestion": "Integrate with EHR system via HL7 FHIR interface. Maintain immutable audit log. SLA: clinician review within 4 hours for non-emergency, 15 minutes for critical flags.",
                    "human_review_required": True,
                },
                {
                    "node_id": "NODE-MED-002",
                    "model_or_mode": "mock-model",
                    "entry_point": "POST /api/v1/medical/medication-review",
                    "trigger_instruction": "Submit prescription JSON (patient_id, medications, dosages, contraindication_check_id) with pharmacist_id. Drug interaction pre-check must complete before this endpoint accepts requests.",
                    "execution_suggestion": "Block prescription issuance system until pharmacist approval is recorded. Log all review decisions for regulatory compliance (21 CFR Part 11 for US deployments).",
                    "human_review_required": True,
                },
            ],
            "final_notes": "Mock response — demo mode. Medical AI workflow enforces mandatory human expert review at every critical gate. No autonomous clinical decisions permitted.",
        }
    )
