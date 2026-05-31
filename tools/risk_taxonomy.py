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
}
