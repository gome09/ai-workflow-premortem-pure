"""TC260《网络安全标准实践指南——智能体部署使用安全指引》(2026-07) mappings.

文件编号：TC260-PG-20266A（v1.0-202607），全国网络安全标准化技术委员会秘书处 2026-07 发布。
五阶段：评估 / 准备 / 部署 / 使用 / 停用（官方第 6-10 章）。

⚠️ 产品缺口：本项目四阶段工作流（Stage1-4）无"停用"阶段对应——
   模型/系统退役时的数据清理与交接（第 10 章：停止主程序、备份数据、
   按部署环境清理撤销凭证、确认订阅费用）在本项目工作流中无环节。
   记录于 phase-2-risk-taxonomy.md §5 与本文件 TC260_STAGE_MAP["停用"]=None。

条款摘要存档：.upgrade/reports/tc260-agent-deployment-summary.md

[信源说明]：官方 PDF 通过 WebSearch 检索获取封面/前言/目录/第 1-5 章正文，
确认章节级条款号（第 6-10 章对应五阶段）。五阶段内子条款（a-j 字母项）
文字基于合规媒体解读（模安局 2026-07-07）交叉核对，字母编号与官方文档体例一致，
具体措辞以官方 PDF 为准。详见摘要存档文件"信源说明"章节。

二次复核：2026-07-17——确认正式发布（约 2026-07-06，MLex 等二手来源；本次复核未能重新抓取 tc260.org.cn 原文，
第 1-5 章此前已获官方 PDF、章节级条款号已确认，见上方 [信源说明]），
五阶段结构（评估/准备/部署/使用/停用）不变；[信源说明] 的限定维持不变
（五阶段子条款措辞仍以官方 PDF 为准），待官网原文可访问后逐条核对。
"""

from __future__ import annotations

# 五阶段 ↔ 本项目四阶段工作流映射
TC260_STAGE_MAP: dict[str, str | None] = {
    "评估": "stage_1_failure_mode_identification",
    "准备": "stage_2_workflow_design",
    "部署": "stage_3_stress_test",
    "使用": "stage_4_trigger_strategy",
    "停用": None,  # 产品缺口：本项目无对应环节
}

# 指引安全要求 → control_refs 标签
TC260_CONTROL_REFS: dict[str, list[str]] = {
    "min_privilege": ["TC260_AGENT:MIN_PRIVILEGE"],
    "directory_access_limit": ["TC260_AGENT:DIR_ACCESS_LIMIT"],
    "sensitive_data_minimal": ["TC260_AGENT:SENSITIVE_DATA_MINIMAL"],
    "human_oversight": ["TC260_AGENT:HUMAN_OVERSIGHT"],
    "resource_limit": ["TC260_AGENT:RESOURCE_LIMIT"],
    "audit_log": ["TC260_AGENT:AUDIT_LOG"],
}

# risk_type → TC260 安全要求映射
TC260_RISK_REFS: dict[str, list[str]] = {
    "over_autonomy": ["TC260_AGENT:MIN_PRIVILEGE", "TC260_AGENT:HUMAN_OVERSIGHT"],
    "unbounded_consumption": ["TC260_AGENT:RESOURCE_LIMIT"],
    "system_prompt_leakage": ["TC260_AGENT:SENSITIVE_DATA_MINIMAL"],
    "sensitive_info": ["TC260_AGENT:SENSITIVE_DATA_MINIMAL"],
    "policy_gap": ["TC260_AGENT:HUMAN_OVERSIGHT"],
    "unsafe_instruction": ["TC260_AGENT:MIN_PRIVILEGE"],
}
