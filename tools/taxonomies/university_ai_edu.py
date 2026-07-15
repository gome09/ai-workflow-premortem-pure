# tools/taxonomies/university_ai_edu.py
"""
University AI risk taxonomy extensions.
Six new risk types specific to Chinese university AI project approval.
Additive — does not replace the existing 7 standard risk types.

Standards referenced:
  PIPL   — 中华人民共和国个人信息保护法 (2021)
  GENAI  — 生成式人工智能服务管理暂行办法 (2023)
  UNESCO — UNESCO Recommendation on the Ethics of AI (2021)
  NIST   — NIST AI RMF (2023)
  EDU    — 教育部相关 AI 治理政策
"""

from __future__ import annotations

UNIV_RISK_REFS: dict[str, list[str]] = {
    "student_data_privacy": [
        "PIPL:Article_28_Sensitive_Personal_Info",
        "PIPL:Article_39_Cross_Border_Transfer",
        "EDU:MoE_2022_Student_Data_Governance",
    ],
    "academic_integrity": [
        "GENAI:Article_11_Education_Content",
        "EDU:Academic_Integrity_AI_Use_Policy",
        "UNESCO_AI:Principle_3_Safety_And_Security",
    ],
    "model_bias_edu": [
        "UNESCO_AI:Principle_8_Fairness_NonDiscrimination",
        "NIST_AI_RMF:GOVERN_6.2_Bias_Mitigation",
        "NIST_AI_RMF:MEASURE_2.5_Bias_Testing",
    ],
    "irb_noncompliance": [
        "PIPL:Article_13_Consent_Basis",
        "EDU:IRB_Human_Subject_Protection_Policy",
        "UNESCO_AI:Principle_6_Privacy_DataGovernance",
    ],
    "data_governance_gap": [
        "PIPL:Article_51_Security_Measures",
        "PIPL:Article_17_Transparency_Obligation",
        "EDU:MoE_2022_Data_Governance",
        "NIST_AI_RMF:GOVERN_1.4_Data_Privacy",
    ],
    "over_reliance_edu": [
        "UNESCO_AI:Principle_4_Human_Agency_Oversight",
        "GENAI:Article_4_Scientific_Literacy",
        "NIST_AI_RMF:GOVERN_5.1_Human_Override",
    ],
}

UNIV_CONTROL_REFS: dict[str, list[str]] = {
    "student_data_privacy": [
        "CONTROL:DATA_MINIMIZATION",
        "CONTROL:ACCESS_CONTROL_RBAC",
        "CONTROL:ANONYMIZATION_REQUIRED",
        "CONTROL:RETENTION_POLICY_ENFORCED",
    ],
    "academic_integrity": [
        "CONTROL:AI_USE_DISCLOSURE_REQUIRED",
        "CONTROL:HUMAN_FINAL_ASSESSMENT",
        "CONTROL:OUTPUT_WATERMARKING",
        "CONTROL:USAGE_AUDIT_LOG",
    ],
    "model_bias_edu": [
        "CONTROL:BIAS_AUDIT_REQUIRED",
        "CONTROL:DISAGGREGATED_EVALUATION",
        "CONTROL:HUMAN_REVIEW_GATE",
        "CONTROL:FAIRNESS_METRIC_REPORTING",
    ],
    "irb_noncompliance": [
        "CONTROL:ETHICS_COMMITTEE_APPROVAL",
        "CONTROL:INFORMED_CONSENT_REQUIRED",
        "CONTROL:DATA_USE_AGREEMENT",
        "CONTROL:PARTICIPANT_RIGHT_TO_WITHDRAW",
    ],
    "data_governance_gap": [
        "CONTROL:DATA_GOVERNANCE_POLICY",
        "CONTROL:RETENTION_LIMIT",
        "CONTROL:SECURITY_ASSESSMENT",
        "CONTROL:THIRD_PARTY_AUDIT",
    ],
    "over_reliance_edu": [
        "CONTROL:AI_LITERACY_TRAINING",
        "CONTROL:HUMAN_FINAL_DECISION",
        "CONTROL:USAGE_TRANSPARENCY",
        "CONTROL:OVERRIDE_MECHANISM",
    ],
}

UNIV_ATTACK_REFS: dict[str, list[str]] = {
    "student_identity_inference": [
        "PIPL:Article_28_Sensitive_Personal_Info",
        "UNESCO_AI:Principle_6_Privacy_DataGovernance",
    ],
    "academic_cheating_abuse": [
        "GENAI:Article_11_Education_Content",
        "EDU:Academic_Integrity_AI_Use_Policy",
    ],
    "demographic_bias_probe": [
        "UNESCO_AI:Principle_8_Fairness_NonDiscrimination",
        "NIST_AI_RMF:MEASURE_2.5_Bias_Testing",
    ],
    "data_scope_creep": [
        "PIPL:Article_6_Data_Minimization",
        "CONTROL:DATA_MINIMIZATION",
    ],
}

UNIV_ATTACK_CONTROL_REFS: dict[str, list[str]] = {
    "student_identity_inference": UNIV_CONTROL_REFS["student_data_privacy"],
    "academic_cheating_abuse": UNIV_CONTROL_REFS["academic_integrity"],
    "demographic_bias_probe": UNIV_CONTROL_REFS["model_bias_edu"],
    "data_scope_creep": UNIV_CONTROL_REFS["data_governance_gap"],
}
