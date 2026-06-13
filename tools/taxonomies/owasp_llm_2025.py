from __future__ import annotations

OWASP_RISK_REFS: dict[str, list[str]] = {
    "prompt_injection": ["OWASP_LLM_2025:LLM01_PROMPT_INJECTION"],
    "sensitive_info": ["OWASP_LLM_2025:LLM02_SENSITIVE_INFORMATION_DISCLOSURE"],
    "unsupported_claim": ["OWASP_LLM_2025:LLM09_MISINFORMATION"],
    "over_autonomy": ["OWASP_LLM_2025:LLM06_EXCESSIVE_AGENCY"],
    "unsafe_instruction": [
        "OWASP_LLM_2025:LLM04_DATA_AND_MODEL_POISONING",
        "OWASP_LLM_2025:LLM06_EXCESSIVE_AGENCY",
    ],
    "source_untrusted": ["OWASP_LLM_2025:LLM03_SUPPLY_CHAIN"],
    "policy_gap": ["OWASP_LLM_2025:LLM06_EXCESSIVE_AGENCY"],
}

OWASP_ATTACK_REFS: dict[str, list[str]] = {
    "direct_prompt_injection": ["OWASP_LLM_2025:LLM01_PROMPT_INJECTION"],
    "indirect_prompt_injection": ["OWASP_LLM_2025:LLM01_PROMPT_INJECTION"],
    "secret_exfiltration": ["OWASP_LLM_2025:LLM02_SENSITIVE_INFORMATION_DISCLOSURE"],
    "fake_citation": ["OWASP_LLM_2025:LLM09_MISINFORMATION"],
    "source_poisoning": [
        "OWASP_LLM_2025:LLM03_SUPPLY_CHAIN",
        "OWASP_LLM_2025:LLM04_DATA_AND_MODEL_POISONING",
    ],
    "tool_overreach": ["OWASP_LLM_2025:LLM06_EXCESSIVE_AGENCY"],
    "excessive_agency": ["OWASP_LLM_2025:LLM06_EXCESSIVE_AGENCY"],
    "policy_bypass": ["OWASP_LLM_2025:LLM06_EXCESSIVE_AGENCY"],
    "evaluator_gaming": ["OWASP_LLM_2025:LLM09_MISINFORMATION"],
    "unsafe_autonomy": ["OWASP_LLM_2025:LLM06_EXCESSIVE_AGENCY"],
    "unsupported_claim": ["OWASP_LLM_2025:LLM09_MISINFORMATION"],
}
