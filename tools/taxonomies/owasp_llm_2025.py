"""OWASP LLM Top 10 2025 risk/attack taxonomy mappings.

LLM08 (Vector and Embedding Weaknesses) 缓办：本项目当前无 RAG/向量检索组件，
引入 RAG 时激活。记录于 phase-2-risk-taxonomy.md T2.1 / spec §3.5。
"""

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
    "improper_output_handling": ["OWASP_LLM_2025:LLM05_IMPROPER_OUTPUT_HANDLING"],
    "system_prompt_leakage": ["OWASP_LLM_2025:LLM07_SYSTEM_PROMPT_LEAKAGE"],
    "unbounded_consumption": ["OWASP_LLM_2025:LLM10_UNBOUNDED_CONSUMPTION"],
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
