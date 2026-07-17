"""NIST AI 600-1 Generative AI Profile action-item references.

对标：NIST-AI-600-1 (2024-07-26 发布)，Generative AI Profile 的 12 类风险动作项。
本文件引用**具体动作项编号**（如 MS-2.7-008），升级现有 nist_ai_rmf.py 的大类字母标签。

核对日期：2026-07-14。NIST AI RMF 1.0 正在修订中（无新版号/日期）；
NIST AI Agent Interoperability Profile 预告 2026 Q4 发布——
发布后需回头更新条款号（见 phase-2-risk-taxonomy.md T2.6）。

条款号格式：NIST_AI_600_1:<FUNCTION>-<CATEGORY>-<NUM>
  FUNCTION: GV(GOVERN) / MS(MEASURE) / MP(MAP) / MN(MANAGE)

Web 核对结论（2026-07-14，主源 https://www.nist.gov/itl/ai-risk-management-framework）：
  - MS-2.7-008  已核实（scfconnect.com AAT-17.5 + CSA AICM AID 44 均直接映射）
  - GV-1.3-002  已核实（CSA AICM AID 44 直接映射）
  - MS-2.10-002 子类别 MS-2.10 已确认属 Data Privacy，-002 后缀 [存疑，待人工核对]
  - MS-2.5-005  子类别 MS-2.5 存在，-005 后缀 [存疑，待人工核对]
  - MS-2.5-003  子类别 MS-2.5 存在，-003 后缀 [存疑，待人工核对]
  - MS-2.11-001 子类别 MS-2.11 存在，-001 后缀 [存疑，待人工核对]

二次复核：2026-07-17——联网仍未获官方原文；MS-2.10-002 连存在性都未证实，
全部 [存疑] 标注维持。唯一解决路径：人工直连 nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf 第 3 节逐字核对。
"""

from __future__ import annotations

# risk_type → Generative AI Profile 具体动作项
NIST_GAI_ACTION_REFS: dict[str, list[str]] = {
    "prompt_injection": ["NIST_AI_600_1:MS-2.7-008"],  # 已核实：GAI 红队/对抗性测试
    "sensitive_info": ["NIST_AI_600_1:MS-2.10-002"],  # [存疑，待人工核对] 隐私风险度量
    "unsupported_claim": ["NIST_AI_600_1:MS-2.5-005"],  # [存疑，待人工核对] Confabulation 度量
    "over_autonomy": ["NIST_AI_600_1:GV-1.3-002"],  # 已核实：人类监督程度界定
    "unsafe_instruction": ["NIST_AI_600_1:MS-2.7-008"],  # 已核实：对抗性评估
    "source_untrusted": ["NIST_AI_600_1:MS-2.5-003"],  # [存疑，待人工核对] 信息完整性校验
    "policy_gap": ["NIST_AI_600_1:GV-1.3-002"],  # 已核实：治理/监督
    "improper_output_handling": ["NIST_AI_600_1:MS-2.5-005"],  # [存疑，待人工核对] 输出净化
    "system_prompt_leakage": ["NIST_AI_600_1:MS-2.7-008"],  # 已核实：对抗性测试
    "unbounded_consumption": ["NIST_AI_600_1:MS-2.11-001"],  # [存疑，待人工核对] 资源滥用监控
}

# 动作项编号 → 中文摘要 + 来源条款
NIST_GAI_ACTION_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "MS-2.7-008": {
        "zh": "对 GAI 系统进行红队测试与对抗性评估，覆盖越狱、提示注入、敏感信息外泄。",
        "source": "NIST AI 600-1 §MS-2.7 (GAI 资源滥用/对抗性) [已核实: AICM AID 44 + scfconnect AAT-17.5]",
    },
    "MS-2.10-002": {
        "zh": "建立 GAI 隐私风险度量，识别训练/推理数据中的个人信息暴露。",
        "source": "NIST AI 600-1 §MS-2.10 (隐私) [存疑，待人工核对: -002 后缀未直接核实]",
    },
    "MS-2.5-005": {
        "zh": "度量 GAI 输出的事实准确性 / Confabulation，建立输出净化流程。",
        "source": "NIST AI 600-1 §MS-2.5 (有害内容/错误信息) [存疑，待人工核对: -005 后缀未直接核实]",
    },
    "GV-1.3-002": {
        "zh": "界定人类对 GAI 决策的监督程度与 Override 权限。",
        "source": "NIST AI 600-1 §GV-1.3 (人类监督) [已核实: AICM AID 44]",
    },
    "MS-2.5-003": {
        "zh": "校验 GAI 引用信息源的完整性与可信度。",
        "source": "NIST AI 600-1 §MS-2.5 (信息完整性) [存疑，待人工核对: -003 后缀未直接核实]",
    },
    "MS-2.11-001": {
        "zh": "监控 GAI 资源消耗（算力/调用次数），防止滥用与成本失控。",
        "source": "NIST AI 600-1 §MS-2.11 (价值链/资源) [存疑，待人工核对: -001 后缀未直接核实]",
    },
}
