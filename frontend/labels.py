# frontend/labels.py
"""前端中文标签与展示辅助。

集中管理"内部枚举 / 状态码 → 中文"的映射，供 app.py 与在用组件复用，
避免把 blocker_type / required_resolution / lifecycle 等原始英文枚举、
或裸露的异常 / API 路径直接展示给普通用户。

约定：所有查表都通过 ``zh()`` 走"查不到就回退原值"的策略，保证即使出现
未覆盖的新枚举也不会丢信息，只是暂时显示英文原值。
"""

from __future__ import annotations

# ── 严重程度 ────────────────────────────────────────────────────────────────
SEVERITY_ZH = {"critical": "危急", "high": "高", "medium": "中", "low": "低"}

# ── 安全发现风险类型（与 core/models.py SafetyFinding.risk_type 枚举对齐）─────
RISK_TYPE_ZH = {
    "prompt_injection": "提示词注入",
    "sensitive_info": "敏感信息泄露",
    "unsupported_claim": "缺乏证据支撑",
    "over_autonomy": "过度自主",
    "unsafe_instruction": "不安全指令",
    "source_untrusted": "来源不可信",
    "policy_gap": "策略覆盖缺口",
    "improper_output_handling": "输出处理不当",  # LLM05
    "system_prompt_leakage": "系统提示词泄露",  # LLM07
    "unbounded_consumption": "资源无限消耗",  # LLM10
}

# ── 阻断类型（简洁名词，用于标签展示）──────────────────────────────────────
BLOCKER_TYPE_ZH = {
    "missing_stage_output": "缺少阶段结果",
    "stale_dependency": "依赖已过期",
    "pending_action": "待处理人工动作",
    "rejected_action": "内容被驳回",
    "unresolved_escalation": "未批准的升级项",
    "parser_error": "解析失败",
    "safety_finding": "安全风险",
    "evidence_gap": "证据缺口",
    "policy_gap": "策略覆盖缺口",
    "eval_failure": "评测失败",
    "redteam_coverage": "红队覆盖不足",
    "eval_regression": "评测回归",
    "trace_backfill_gap": "追踪回填缺口",
    "final_governance": "治理未闭环",
}

# ── 人工动作来源（source_type → 中文摘要标签）──────────────────────────────
# 与后端 core.oversight_service._ACTION_SOURCE_LABEL 保持一致，供对话区实时
# 人工监督摘要按来源归类展示。
ACTION_SOURCE_ZH = {
    "flag": "有内容需要人工核验",
    "failure_mode": "有高风险失败模式需要确认",
    "evidence_gap": "证据引用不足，需要补充",
    "evidence_low_credibility": "有证据可信度偏低，需要核验",
    "evidence_unverified_for_high_risk": "高风险结论的证据尚未核验",
    "oversight_policy": "有工作流节点的监督策略需要处理",
    "policy_gap": "工作流设计存在覆盖缺口",
    "stress_test": "压力测试结果需要人工决定",
    "eval_coverage": "高风险节点缺少测试用例覆盖",
    "eval_case": "有测试用例未通过，需要处理",
    "eval_run": "有测试运行结果需要人工复核",
    "trigger_method": "有触发方式需要人工审核确认",
    "safety_finding": "有安全风险需要处理",
    "parser": "AI 输出解析失败，需要人工修复",
    "redteam_gap": "红队测试覆盖不足",
    "redteam_case": "有红队用例需要处理",
    "trace_backfill_gap": "生产追踪数据尚未回填为测试用例",
    "eval_regression": "评测结果出现回归",
    "human_action": "有事项需要人工处理",
}

# ── 所需解除操作 ────────────────────────────────────────────────────────────
REQUIRED_RESOLUTION_ZH = {
    "run_stage": "运行当前阶段",
    "rerun_stage": "重跑当前阶段",
    "resolve_action": "处理人工动作",
    "verify_evidence": "核验证据",
    "edit_stage_output": "编辑阶段输出",
    "revise_stage": "修订当前阶段",
    "back_stage": "回退阶段",
    "approve_escalation": "批准升级项",
    "resolve_safety_finding": "处理安全发现",
    "create_eval_dataset_from_stage3": "从阶段三生成评测数据集",
    "add_eval_cases_to_dataset": "向数据集补充评测用例",
    "set_eval_baseline": "设定评测基线",
    "create_eval_experiment": "创建评测实验",
    "run_eval_experiment": "运行评测实验",
    "compare_eval_experiment": "对比评测实验",
    "generate_redteam_cases": "生成红队用例",
    "approve_redteam_case": "批准红队用例",
    "sync_redteam_eval_case": "同步红队评测用例",
    "create_redteam_dataset": "创建红队数据集",
    "trace_to_eval_case": "追踪转评测用例",
    "create_trace_backfill_dataset": "创建追踪回填数据集",
}

# ── 阶段生命周期 ────────────────────────────────────────────────────────────
STAGE_LIFECYCLE_ZH = {
    "not_started": "未开始",
    "running": "进行中",
    "review": "待审核",
    "blocked": "已阻断",
    "ready_to_advance": "可推进",
    "approved": "已通过",
    "stale": "已过期",
}

# ── 通用状态 ────────────────────────────────────────────────────────────────
STATUS_ZH = {
    "open": "待处理",
    "resolved": "已处理",
    "dismissed": "已关闭",
    "passed": "通过",
    "failed": "未通过",
    "blocked": "已阻断",
    "skipped": "已跳过",
    "error": "错误",
    "draft": "草稿",
    "approved": "已批准",
    "rejected": "已驳回",
    "synced": "已同步",
    "pending": "待处理",
    "running": "进行中",
    "completed": "已完成",
    "unknown": "未知",
}

# ── 工作流执行模式 / 中断适配器状态（/health 字段）──────────────────────────
EXEC_MODE_ZH = {
    "single_step": "单步（稳定）",
    "langgraph_interrupt": "LangGraph 中断（实验）",
    "unknown": "未知",
}

ADAPTER_STATUS_ZH = {
    "healthy": "正常",
    "degraded": "降级",
    "unavailable": "不可用",
    "disabled": "未启用",
    "not_configured": "未配置",
    "unknown": "未知",
}

# ── 决策原因（内部代码，仅少数常见值做友好化，其余回退原值）────────────────
DECISION_REASON_ZH = {
    "read_stage_advancement_decision": "读取阶段推进判定",
    "chat_message_processed": "对话消息已处理",
    "user_review_approve": "用户确认推进",
    "report_stage_advancement_snapshot": "生成报告推进快照",
}


def zh(mapping: dict[str, str], key: object, default: str | None = None) -> str:
    """通用查表：命中则返回中文，否则回退到默认值或原始 key（不丢信息）。"""
    if key is None:
        return default if default is not None else "-"
    text = mapping.get(str(key))
    if text is not None:
        return text
    if default is not None:
        return default
    return str(key)


def severity_zh(value: object) -> str:
    return zh(SEVERITY_ZH, value)


def risk_type_zh(value: object) -> str:
    return zh(RISK_TYPE_ZH, value)


def exec_mode_zh(value: object) -> str:
    return zh(EXEC_MODE_ZH, value)


def adapter_status_zh(value: object) -> str:
    return zh(ADAPTER_STATUS_ZH, value)


def blocker_type_zh(value: object) -> str:
    return zh(BLOCKER_TYPE_ZH, value)


def action_source_zh(value: object) -> str:
    return zh(ACTION_SOURCE_ZH, value, default="有事项需要人工处理")


def resolution_zh(value: object) -> str:
    return zh(REQUIRED_RESOLUTION_ZH, value)


def lifecycle_zh(value: object) -> str:
    return zh(STAGE_LIFECYCLE_ZH, value)


def status_zh(value: object) -> str:
    return zh(STATUS_ZH, value)


def decision_reason_zh(value: object) -> str:
    return zh(DECISION_REASON_ZH, value)


def hard_blocker_zh(is_hard: object) -> str:
    """硬阻断 / 可批准豁免。"""
    return "必须处理" if is_hard else "可批准豁免"


def friendly_error(exc: object = None, action: str = "加载") -> str:
    """把异常 / HTTP 错误包装成面向用户的中文短句，避免暴露英文堆栈。"""
    return f"{action}失败，请稍后重试或联系管理员。"
