# tools/risk_taxonomy.py
from __future__ import annotations

RISK_DESCRIPTIONS = {
    "prompt_injection": "文本包含疑似提示注入或越权控制模型的内容。",
    "sensitive_info": "文本包含疑似密钥、令牌、口令或敏感信息。",
    "unsupported_claim": "文本包含高确定性断言，但缺少证据支撑的风险。",
    "over_autonomy": "文本暗示跳过人工确认或让 AI 自主执行高风险动作。",
    "unsafe_instruction": "文本包含不安全或不合规的执行建议。",
    "source_untrusted": "高风险结论依赖低可信或未知来源。",
    "policy_gap": "当前输出暴露了人工监督或治理策略缺口。",
    "improper_output_handling": "AI 输出包含未净化的可执行内容（脚本、SQL、shell 命令），下游直接消费可能导致注入。",
    "system_prompt_leakage": "输入试图诱导系统泄露其系统提示词/初始指令，构成门禁策略绕过线索。",
    "unbounded_consumption": "会话级 LLM 调用次数或 token 消耗超过阈值，存在资源滥用或成本失控风险。",
}

_UNIVERSITY_AI_EXTRA: dict[str, str] = {
    "student_data_privacy": "涉及学生个人信息、学习记录、行为数据的隐私侵犯风险，须符合《个人信息保护法》。",
    "academic_integrity": "AI 系统被滥用于学术不诚信（作弊、代写、抄袭）的风险，及现有防护机制是否足够。",
    "model_bias_edu": "模型在不同学生群体（性别、民族、经济背景、学业水平）间存在系统性输出偏差。",
    "irb_noncompliance": "数据收集或使用不符合人类受试者保护规范（IRB/伦理委员会），或未取得知情同意。",
    "data_governance_gap": "数据管理、存储、访问控制、保留期限不符合教育数据保护要求。",
    "over_reliance_edu": "学生或教师过度依赖 AI 系统，削弱独立思考和批判性评估能力，影响教育目标。",
}

_MEDICAL_AI_EXTRA: dict[str, str] = {
    "misdiagnosis_risk": "模型输出错误诊断或治疗建议，包括假阳性/假阴性率超限及缺乏置信度标注，直接危及患者安全。",
    "patient_data_privacy": "PHI（受保护健康信息）在采集、存储、传输过程中违反 HIPAA、GDPR 及《个人信息保护法》第 28 条要求。",
    "informed_consent_gap": "患者在 AI 辅助诊疗前未充分知情或未有效表达同意，违反 FDA SaMD 及《医疗机构管理条例》要求。",
    "algorithmic_bias_medical": "训练数据偏差导致特定患者群体（老年人、儿科、少数民族、罕见病）诊疗结果不公平，违反 WHO AI 伦理原则。",
    "over_reliance_clinical": "临床医生过度依赖 AI 输出、削弱独立判断能力，在 AI 失效时缺乏有效处置能力。",
    "audit_trail_gap": "AI 辅助决策记录不完整，无法满足 HIPAA 审计控制要求（§164.312）或 IEC 62304 事后追溯监管审查标准。",
}


def get_risk_descriptions(profile: str = "default") -> dict[str, str]:
    """Return risk-type description mapping for *profile*.

    The university_ai profile extends the base 7 types with 6 education-specific
    types. The medical_ai profile extends with 6 clinical AI-specific types.
    Unknown profiles return the base dict unchanged.
    """
    if profile == "university_ai":
        return {**RISK_DESCRIPTIONS, **_UNIVERSITY_AI_EXTRA}
    if profile == "medical_ai":
        return {**RISK_DESCRIPTIONS, **_MEDICAL_AI_EXTRA}
    return dict(RISK_DESCRIPTIONS)
