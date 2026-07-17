"""OWASP Top 10 for Agentic Applications 2026 (ASI01-ASI10) mappings.

对标：OWASP GenAI Security Project — Agentic Applications Top 10 (2026)。
本项目是 LangGraph Agent 工作流平台，这是当前最直接适用的新标准。

⚠️ 初稿映射：落地第一步是通读 genai.owasp.org 的 ASI 正式定义后逐条复核，
映射不确定的条目宁缺毋滥（spec §5）。下方映射表标注 [已复核]/[存疑]。

核对日期：2026-07-14（通过 WebFetch 抓取 genai.owasp.org 及两个交叉来源核对）。

二次复核：2026-07-17（WebSearch 多源交叉，ASI01–ASI10 名称与本表一致，无需改动；
官方 PDF 逐字定名仍待人工核对 ASI03/04/08 措辞变体）。

ASI01-ASI10 编号与名称对应表（已核对，两来源一致）：
    ASI01  Agent Goal Hijack                    智能体目标劫持
    ASI02  Tool Misuse and Exploitation         工具滥用与利用
    ASI03  Identity and Privilege Abuse         身份与权限滥用
    ASI04  Agentic Supply Chain Vulnerabilities 智能体供应链风险
    ASI05  Unexpected Code Execution            意外代码执行
    ASI06  Memory and Context Poisoning         记忆与上下文投毒
    ASI07  Insecure Inter-Agent Communication   智能体间通信不安全
    ASI08  Cascading Failures                   级联失败
    ASI09  Human-Agent Trust Exploitation       人机信任滥用
    ASI10  Rogue Agents                         失控智能体

⚠️ 关于 ``unbounded_consumption`` 映射（设计方案 §2.3 初稿曾拟映射到 ASI07）：
    经核对，ASI07 为 "Insecure Inter-Agent Communication"（智能体间通信不安全），
    **并非** Resource Abuse，原映射错误。按“宁缺毋滥”原则已删除该条映射，
    不保留错误映射。ASI08 "Cascading Failures" 在官方描述中覆盖 resource exhaustion /
    retry storms / infinite loops，理论上与 unbounded_consumption 更相关，但属于
    新增映射、超出本任务“复核初稿”范围，留待 Wave 2 mapper 接入时再评估，不在本表强行落入。
    故当前 ASI_RISK_REFS 不含 ``unbounded_consumption``。

evaluator_gaming → ASI10 标注 [存疑]：ASI10 "Rogue Agents" 官方场景含 “reward hacking /
optimization abuse（奖励破解与优化滥用）”，与 evaluator_gaming（操纵评测器过关）语义相关，
映射有据；但本任务范围仅复核初稿，落地时仍建议人工再确认，故保留 [存疑] 标记。

无直接 ASI 对应、不强行映射的内部 attack_type：
    secret_exfiltration / fake_citation / unsupported_claim
    （secret_exfiltration 更贴近 OWASP LLM2025 LLM02；fake_citation/unsupported_claim
     更贴近 LLM09；ASI 暂无独立“幻觉/误导”或“敏感信息泄露”条目。）
"""

from __future__ import annotations

# 内部 attack_type → ASI 映射
ASI_ATTACK_REFS: dict[str, list[str]] = {
    "direct_prompt_injection": ["OWASP_ASI_2026:ASI01"],  # Agent Goal Hijack [已复核]
    "indirect_prompt_injection": ["OWASP_ASI_2026:ASI01"],  # Agent Goal Hijack [已复核]
    "tool_overreach": ["OWASP_ASI_2026:ASI02"],  # Tool Misuse & Exploitation [已复核]
    "excessive_agency": ["OWASP_ASI_2026:ASI03"],  # Identity & Privilege Abuse [已复核]
    "unsafe_autonomy": ["OWASP_ASI_2026:ASI03"],  # Identity & Privilege Abuse [已复核]
    "source_poisoning": ["OWASP_ASI_2026:ASI06"],  # Memory & Context Poisoning [已复核]
    "policy_bypass": ["OWASP_ASI_2026:ASI09"],  # Human-Agent Trust Exploitation [已复核]
    "evaluator_gaming": ["OWASP_ASI_2026:ASI10"],  # Rogue Agents [存疑，落地时复核]
    # secret_exfiltration / fake_citation / unsupported_claim: 无直接 ASI 对应，不强行映射
}

# risk_type → ASI 映射
# 注：unbounded_consumption 已删除——ASI07 非 Resource Abuse，见文件头说明。
ASI_RISK_REFS: dict[str, list[str]] = {
    "prompt_injection": ["OWASP_ASI_2026:ASI01"],  # Agent Goal Hijack
    "over_autonomy": ["OWASP_ASI_2026:ASI03"],  # Identity & Privilege Abuse
    "system_prompt_leakage": ["OWASP_ASI_2026:ASI01"],  # Goal Hijack 手段之一
    "policy_gap": ["OWASP_ASI_2026:ASI09"],  # Human-Agent Trust Exploitation
}
