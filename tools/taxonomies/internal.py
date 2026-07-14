from __future__ import annotations

INTERNAL_RISK_REFS: dict[str, list[str]] = {
    "prompt_injection": ["INTERNAL:AI_GOV:PROMPT_INJECTION"],
    "sensitive_info": ["INTERNAL:AI_GOV:SENSITIVE_INFORMATION"],
    "unsupported_claim": ["INTERNAL:AI_GOV:UNSUPPORTED_CLAIM"],
    "over_autonomy": ["INTERNAL:AI_GOV:OVER_AUTONOMY"],
    "unsafe_instruction": ["INTERNAL:AI_GOV:POLICY_BYPASS"],
    "source_untrusted": ["INTERNAL:AI_GOV:SOURCE_TRUST"],
    "policy_gap": ["INTERNAL:AI_GOV:HUMAN_OVERSIGHT_GAP"],
    "improper_output_handling": ["INTERNAL:AI_GOV:UNSAFE_OUTPUT"],
    "system_prompt_leakage": ["INTERNAL:AI_GOV:SYSTEM_PROMPT_LEAKAGE"],
    "unbounded_consumption": ["INTERNAL:AI_GOV:UNBOUNDED_CONSUMPTION"],
}

INTERNAL_ATTACK_REFS: dict[str, list[str]] = {
    "direct_prompt_injection": ["INTERNAL:REDTEAM:DIRECT_PROMPT_INJECTION"],
    "indirect_prompt_injection": ["INTERNAL:REDTEAM:INDIRECT_PROMPT_INJECTION"],
    "secret_exfiltration": ["INTERNAL:REDTEAM:SECRET_EXFILTRATION"],
    "fake_citation": ["INTERNAL:REDTEAM:FAKE_CITATION"],
    "source_poisoning": ["INTERNAL:REDTEAM:SOURCE_POISONING"],
    "tool_overreach": ["INTERNAL:REDTEAM:TOOL_OVERREACH"],
    "excessive_agency": ["INTERNAL:REDTEAM:EXCESSIVE_AGENCY"],
    "policy_bypass": ["INTERNAL:REDTEAM:POLICY_BYPASS"],
    "evaluator_gaming": ["INTERNAL:REDTEAM:EVALUATOR_GAMING"],
    "unsafe_autonomy": ["INTERNAL:REDTEAM:UNSAFE_AUTONOMY"],
    "unsupported_claim": ["INTERNAL:REDTEAM:UNSUPPORTED_CLAIM"],
}

DEFAULT_CONTROL_REFS: dict[str, list[str]] = {
    "prompt_injection": ["CONTROL:INPUT_OUTPUT_SANITIZATION", "CONTROL:HUMAN_REVIEW_GATE"],
    "sensitive_info": ["CONTROL:SECRET_REDACTION", "CONTROL:DATA_MINIMIZATION"],
    "unsupported_claim": ["CONTROL:EVIDENCE_REQUIRED", "CONTROL:HUMAN_FACT_CHECK"],
    "over_autonomy": ["CONTROL:HUMAN_APPROVAL_REQUIRED", "CONTROL:ACTION_SCOPE_LIMIT"],
    "unsafe_instruction": ["CONTROL:POLICY_ENFORCEMENT", "CONTROL:HUMAN_REVIEW_GATE"],
    "source_untrusted": ["CONTROL:SOURCE_CREDIBILITY_CHECK", "CONTROL:EVIDENCE_VERIFICATION"],
    "policy_gap": ["CONTROL:OVERSIGHT_POLICY_REQUIRED", "CONTROL:STAGE_GATE_BLOCKER"],
    "improper_output_handling": ["CONTROL:OUTPUT_SANITIZATION", "CONTROL:HUMAN_REVIEW_GATE"],
    "system_prompt_leakage": ["CONTROL:SYSTEM_PROMPT_PROTECTION", "CONTROL:HUMAN_REVIEW_GATE"],
    "unbounded_consumption": ["CONTROL:RATE_LIMITING", "CONTROL:USAGE_MONITORING"],
}

ATTACK_CONTROL_REFS: dict[str, list[str]] = {
    "direct_prompt_injection": DEFAULT_CONTROL_REFS["prompt_injection"],
    "indirect_prompt_injection": DEFAULT_CONTROL_REFS["prompt_injection"],
    "secret_exfiltration": DEFAULT_CONTROL_REFS["sensitive_info"],
    "fake_citation": DEFAULT_CONTROL_REFS["unsupported_claim"],
    "source_poisoning": DEFAULT_CONTROL_REFS["source_untrusted"],
    "tool_overreach": DEFAULT_CONTROL_REFS["over_autonomy"],
    "excessive_agency": DEFAULT_CONTROL_REFS["over_autonomy"],
    "policy_bypass": DEFAULT_CONTROL_REFS["policy_gap"],
    "evaluator_gaming": ["CONTROL:JUDGE_HUMAN_CALIBRATION", "CONTROL:REGRESSION_GATE"],
    "unsafe_autonomy": DEFAULT_CONTROL_REFS["over_autonomy"],
    "unsupported_claim": DEFAULT_CONTROL_REFS["unsupported_claim"],
}
