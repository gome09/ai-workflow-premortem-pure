from __future__ import annotations

from typing import Any

from core.version import APP_VERSION
from tools.taxonomies.internal import (
    ATTACK_CONTROL_REFS,
    DEFAULT_CONTROL_REFS,
    INTERNAL_ATTACK_REFS,
    INTERNAL_RISK_REFS,
)
from tools.taxonomies.medical_ai_clinical import MEDICAL_CONTROL_REFS, MEDICAL_RISK_REFS
from tools.taxonomies.microsoft_agent_failure_modes import (
    MICROSOFT_AGENT_ATTACK_REFS,
    MICROSOFT_AGENT_RISK_REFS,
)
from tools.taxonomies.nist_ai_600_1 import NIST_GAI_ACTION_REFS
from tools.taxonomies.nist_ai_rmf import NIST_ATTACK_REFS, NIST_RISK_REFS
from tools.taxonomies.owasp_agentic_2026 import ASI_ATTACK_REFS, ASI_RISK_REFS
from tools.taxonomies.owasp_llm_2025 import OWASP_ATTACK_REFS, OWASP_RISK_REFS
from tools.taxonomies.tc260_agent_deployment import TC260_RISK_REFS
from tools.taxonomies.university_ai_edu import (
    UNIV_CONTROL_REFS,
    UNIV_RISK_REFS,
)


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys([value for value in values if value]))


def refs_for_risk_type(risk_type: str | None) -> list[str]:
    key = str(risk_type or "").lower()
    return _dedupe(
        INTERNAL_RISK_REFS.get(key, [])
        + OWASP_RISK_REFS.get(key, [])
        + NIST_RISK_REFS.get(key, [])
        + NIST_GAI_ACTION_REFS.get(key, [])
        + MICROSOFT_AGENT_RISK_REFS.get(key, [])
        + ASI_RISK_REFS.get(key, [])
        + TC260_RISK_REFS.get(key, [])
    )


def refs_for_attack_type(attack_type: str | None) -> list[str]:
    key = str(attack_type or "").lower()
    return _dedupe(
        INTERNAL_ATTACK_REFS.get(key, [])
        + OWASP_ATTACK_REFS.get(key, [])
        + NIST_ATTACK_REFS.get(key, [])
        + MICROSOFT_AGENT_ATTACK_REFS.get(key, [])
        + ASI_ATTACK_REFS.get(key, [])
    )


def controls_for_risk_type(risk_type: str | None) -> list[str]:
    return _dedupe(DEFAULT_CONTROL_REFS.get(str(risk_type or "").lower(), []))


def controls_for_attack_type(attack_type: str | None) -> list[str]:
    return _dedupe(ATTACK_CONTROL_REFS.get(str(attack_type or "").lower(), []))


def residual_risk_from_severity(severity: str | None, status: str | None = None) -> str:
    if status == "resolved":
        return "low"
    if status == "dismissed":
        return "unknown"
    severity_value = str(severity or "medium").lower()
    return severity_value if severity_value in {"low", "medium", "high", "critical"} else "unknown"


def mitigation_status_from_state(status: str | None) -> str:
    if status == "resolved":
        return "mitigated"
    if status == "dismissed":
        return "dismissed"
    return "open"


def apply_taxonomy_to_safety_finding(finding: Any, domain: str = "default") -> Any:
    existing_refs = list(getattr(finding, "taxonomy_refs", []) or [])
    existing_controls = list(getattr(finding, "control_refs", []) or [])
    risk_type = getattr(finding, "risk_type", None)

    refs = refs_for_risk_type(risk_type)
    controls = controls_for_risk_type(risk_type)

    # T2.5: domain 命中 university_ai/medical_ai 时叠加领域专属标签
    if domain in {"university_ai", "medical_ai"}:
        refs = refs + refs_for_risk_type_extended(risk_type, domain)
        controls = controls + controls_for_risk_type_extended(risk_type, domain)

    finding.taxonomy_refs = _dedupe(existing_refs + refs)
    finding.control_refs = _dedupe(existing_controls + controls)
    if not getattr(finding, "mitigation_status", None) or finding.mitigation_status == "open":
        finding.mitigation_status = mitigation_status_from_state(getattr(finding, "status", None))
    if not getattr(finding, "residual_risk", None) or finding.residual_risk == "unknown":
        finding.residual_risk = residual_risk_from_severity(
            getattr(finding, "severity", None), getattr(finding, "status", None)
        )
    return finding


def apply_taxonomy_to_redteam_case(case: Any) -> Any:
    existing_refs = list(getattr(case, "taxonomy_refs", []) or [])
    existing_controls = list(getattr(case, "control_refs", []) or [])
    attack_type = getattr(case, "attack_type", None)
    case.taxonomy_refs = _dedupe(existing_refs + refs_for_attack_type(attack_type))
    case.control_refs = _dedupe(existing_controls + controls_for_attack_type(attack_type))
    return case


def build_taxonomy_summary(ctx: Any) -> dict[str, Any]:
    safety_refs: dict[str, int] = {}
    redteam_refs: dict[str, int] = {}
    control_refs: dict[str, int] = {}
    unmapped_safety: list[str] = []
    unmapped_redteam: list[str] = []

    for finding in getattr(ctx, "safety_findings", []) or []:
        refs = list(getattr(finding, "taxonomy_refs", []) or [])
        controls = list(getattr(finding, "control_refs", []) or [])
        if not refs:
            unmapped_safety.append(getattr(finding, "finding_id", ""))
        for ref in refs:
            safety_refs[ref] = safety_refs.get(ref, 0) + 1
        for ref in controls:
            control_refs[ref] = control_refs.get(ref, 0) + 1

    for case in getattr(ctx, "redteam_cases", []) or []:
        refs = list(getattr(case, "taxonomy_refs", []) or [])
        controls = list(getattr(case, "control_refs", []) or [])
        if not refs:
            unmapped_redteam.append(getattr(case, "redteam_case_id", ""))
        for ref in refs:
            redteam_refs[ref] = redteam_refs.get(ref, 0) + 1
        for ref in controls:
            control_refs[ref] = control_refs.get(ref, 0) + 1

    return {
        "policy_version": APP_VERSION,
        "runtime_validation": "deferred_by_instruction",
        "safety_taxonomy_ref_counts": dict(sorted(safety_refs.items())),
        "redteam_taxonomy_ref_counts": dict(sorted(redteam_refs.items())),
        "control_ref_counts": dict(sorted(control_refs.items())),
        "unmapped_safety_finding_ids": [item for item in unmapped_safety if item],
        "unmapped_redteam_case_ids": [item for item in unmapped_redteam if item],
    }


def refs_for_risk_type_extended(risk_type: str | None, profile: str = "default") -> list[str]:
    """Like refs_for_risk_type but also checks profile-specific taxonomies.

    For "default" or unknown profiles, behaviour is identical to refs_for_risk_type.
    For "university_ai", returns refs from UNIV_RISK_REFS when the key exists there.
    For "medical_ai", returns refs from MEDICAL_RISK_REFS when the key exists there.
    Both fall back to the standard registries for unrecognised keys.
    """
    key = str(risk_type or "").lower()
    if profile == "university_ai" and key in UNIV_RISK_REFS:
        return _dedupe(UNIV_RISK_REFS[key])
    if profile == "medical_ai" and key in MEDICAL_RISK_REFS:
        return _dedupe(MEDICAL_RISK_REFS[key])
    return refs_for_risk_type(risk_type)


def controls_for_risk_type_extended(risk_type: str | None, profile: str = "default") -> list[str]:
    """Like controls_for_risk_type but also checks profile-specific control refs."""
    key = str(risk_type or "").lower()
    if profile == "university_ai" and key in UNIV_CONTROL_REFS:
        return _dedupe(UNIV_CONTROL_REFS[key])
    if profile == "medical_ai" and key in MEDICAL_CONTROL_REFS:
        return _dedupe(MEDICAL_CONTROL_REFS[key])
    return controls_for_risk_type(risk_type)
