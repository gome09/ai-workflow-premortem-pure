from __future__ import annotations

NIST_RISK_REFS: dict[str, list[str]] = {
    "prompt_injection": ["NIST_AI_RMF:MAP", "NIST_AI_RMF:MANAGE"],
    "sensitive_info": ["NIST_AI_RMF:MEASURE", "NIST_AI_RMF:MANAGE"],
    "unsupported_claim": ["NIST_AI_RMF:MEASURE"],
    "over_autonomy": ["NIST_AI_RMF:GOVERN", "NIST_AI_RMF:MANAGE"],
    "unsafe_instruction": ["NIST_AI_RMF:MANAGE"],
    "source_untrusted": ["NIST_AI_RMF:MAP", "NIST_AI_RMF:MEASURE"],
    "policy_gap": ["NIST_AI_RMF:GOVERN", "NIST_AI_RMF:MANAGE"],
    "improper_output_handling": ["NIST_AI_RMF:MEASURE", "NIST_AI_RMF:MANAGE"],
    "system_prompt_leakage": ["NIST_AI_RMF:MAP", "NIST_AI_RMF:MANAGE"],
    "unbounded_consumption": ["NIST_AI_RMF:MEASURE", "NIST_AI_RMF:MANAGE"],
}

NIST_ATTACK_REFS: dict[str, list[str]] = {
    "direct_prompt_injection": ["NIST_AI_RMF:MAP", "NIST_AI_RMF:MANAGE"],
    "indirect_prompt_injection": ["NIST_AI_RMF:MAP", "NIST_AI_RMF:MANAGE"],
    "secret_exfiltration": ["NIST_AI_RMF:MEASURE", "NIST_AI_RMF:MANAGE"],
    "fake_citation": ["NIST_AI_RMF:MEASURE"],
    "source_poisoning": ["NIST_AI_RMF:MAP", "NIST_AI_RMF:MEASURE"],
    "tool_overreach": ["NIST_AI_RMF:GOVERN", "NIST_AI_RMF:MANAGE"],
    "excessive_agency": ["NIST_AI_RMF:GOVERN", "NIST_AI_RMF:MANAGE"],
    "policy_bypass": ["NIST_AI_RMF:GOVERN", "NIST_AI_RMF:MANAGE"],
    "evaluator_gaming": ["NIST_AI_RMF:MEASURE"],
    "unsafe_autonomy": ["NIST_AI_RMF:GOVERN", "NIST_AI_RMF:MANAGE"],
    "unsupported_claim": ["NIST_AI_RMF:MEASURE"],
}
