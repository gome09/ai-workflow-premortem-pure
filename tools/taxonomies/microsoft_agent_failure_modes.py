from __future__ import annotations

MICROSOFT_AGENT_RISK_REFS: dict[str, list[str]] = {
    "prompt_injection": ["MS_AGENT_FAILURE:PROMPT_INJECTION"],
    "sensitive_info": ["MS_AGENT_FAILURE:SECRET_OR_DATA_LEAKAGE"],
    "unsupported_claim": ["MS_AGENT_FAILURE:UNSUPPORTED_OUTPUT"],
    "over_autonomy": ["MS_AGENT_FAILURE:EXCESSIVE_AGENCY"],
    "unsafe_instruction": ["MS_AGENT_FAILURE:POLICY_BYPASS"],
    "source_untrusted": ["MS_AGENT_FAILURE:UNTRUSTED_TOOL_OR_SOURCE_OUTPUT"],
    "policy_gap": ["MS_AGENT_FAILURE:MISSING_HUMAN_OVERSIGHT"],
    "improper_output_handling": ["MS_AGENT_FAILURE:UNSAFE_OUTPUT"],
    "system_prompt_leakage": ["MS_AGENT_FAILURE:PROMPT_INJECTION"],
    "unbounded_consumption": ["MS_AGENT_FAILURE:EXCESSIVE_AGENCY"],
}

MICROSOFT_AGENT_ATTACK_REFS: dict[str, list[str]] = {
    "direct_prompt_injection": ["MS_AGENT_FAILURE:PROMPT_INJECTION"],
    "indirect_prompt_injection": ["MS_AGENT_FAILURE:INDIRECT_PROMPT_INJECTION"],
    "secret_exfiltration": ["MS_AGENT_FAILURE:SECRET_OR_DATA_LEAKAGE"],
    "fake_citation": ["MS_AGENT_FAILURE:UNSUPPORTED_OUTPUT"],
    "source_poisoning": ["MS_AGENT_FAILURE:UNTRUSTED_TOOL_OR_SOURCE_OUTPUT"],
    "tool_overreach": ["MS_AGENT_FAILURE:EXCESSIVE_AGENCY"],
    "excessive_agency": ["MS_AGENT_FAILURE:EXCESSIVE_AGENCY"],
    "policy_bypass": ["MS_AGENT_FAILURE:POLICY_BYPASS"],
    "evaluator_gaming": ["MS_AGENT_FAILURE:EVALUATOR_GAMING"],
    "unsafe_autonomy": ["MS_AGENT_FAILURE:UNSAFE_AUTONOMY"],
    "unsupported_claim": ["MS_AGENT_FAILURE:UNSUPPORTED_OUTPUT"],
}
