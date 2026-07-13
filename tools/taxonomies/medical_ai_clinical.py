# tools/taxonomies/medical_ai_clinical.py
"""
Medical AI risk taxonomy extensions.
Six new risk types specific to clinical AI governance.
Additive — does not replace the existing 7 standard risk types.

Standards referenced:
  FDA-SaMD  — FDA Software as a Medical Device (SaMD) Guidance (2021)
  ISO14971  — ISO 14971:2019 Risk Management for Medical Devices
  HIPAA     — Health Insurance Portability and Accountability Act (164.xxx = CFR section)
  GDPR      — EU General Data Protection Regulation
  PIPL      — 中华人民共和国个人信息保护法 (2021)
  NIST      — NIST AI RMF (2023)
  WHO       — WHO Ethics and Governance of AI for Health (2021)
  JCI       — Joint Commission International Standards (2023)
  ICH-E6    — ICH E6 Good Clinical Practice
  IEC62304  — IEC 62304:2006 Medical Device Software
"""

from __future__ import annotations

MEDICAL_AI_REFS: dict[str, dict[str, list[str]]] = {
    "misdiagnosis_risk": {
        "taxonomy_refs": ["FDA-SaMD-2021", "ISO14971-2019", "NIST-AI-RMF-1.0"],
        "control_refs": ["HIPAA-164.312", "WHO-Ethics-2021-P4", "JCI-MOI.1"],
    },
    "patient_data_privacy": {
        "taxonomy_refs": ["HIPAA-PHI", "GDPR-Art9", "PIPL-Art28"],
        "control_refs": ["HIPAA-164.514", "GDPR-Art35-DPIA", "NIST-SP800-66"],
    },
    "informed_consent_gap": {
        "taxonomy_refs": ["FDA-SaMD-2021-S3", "ICH-E6-GCP"],
        "control_refs": ["21CFR50", "WHO-Ethics-2021-P3"],
    },
    "algorithmic_bias_medical": {
        "taxonomy_refs": ["NIST-AI-RMF-BIAS", "WHO-Ethics-2021-P6"],
        "control_refs": ["FDA-AI-Action-Plan-2021", "NIST-SP1270"],
    },
    "over_reliance_clinical": {
        "taxonomy_refs": ["FDA-SaMD-2021", "JCI-Standards-2023"],
        "control_refs": ["FDA-AI-Action-Plan-2021-S4", "JCI-MOI.8"],
    },
    "audit_trail_gap": {
        "taxonomy_refs": ["HIPAA-164.312e", "IEC62304-2006"],
        "control_refs": ["HIPAA-164.312-b", "IEC62304-S5.1"],
    },
}

MEDICAL_RISK_REFS: dict[str, list[str]] = {
    risk: data["taxonomy_refs"] for risk, data in MEDICAL_AI_REFS.items()
}

MEDICAL_CONTROL_REFS: dict[str, list[str]] = {
    risk: data["control_refs"] for risk, data in MEDICAL_AI_REFS.items()
}
