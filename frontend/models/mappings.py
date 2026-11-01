# frontend/models/mappings.py
from __future__ import annotations

STRUCTURED_EDIT_SOURCE_TYPES = {"parser", "policy_gap", "evidence_gap", "eval_coverage"}

STATE_LABELS: dict[str, tuple[str, str]] = {
    "init": ("🟡", "收集项目信息"),
    "s1_running": ("🔵", "阶段一：失败模式识别"),
    "s1_review": ("🟠", "阶段一：等待确认"),
    "s2_running": ("🔵", "阶段二：工作流设计"),
    "s2_review": ("🟠", "阶段二：等待确认"),
    "s3_running": ("🔵", "阶段三：压力测试"),
    "s3_review": ("🟠", "阶段三：等待确认"),
    "s4_running": ("🔵", "阶段四：触发方式"),
    "s4_review": ("🟠", "阶段四：等待确认"),
    "complete": ("✅", "评估完成（不代表上线批准）"),
    "error": ("⛔", "工作流错误（已阻断）"),
    "recovery_required": ("🛠️", "需要人工恢复"),
}

# 阻断态：前端必须停止自动推进，只允许显式恢复。
BLOCKED_STATES = {"error", "recovery_required"}

# 可由恢复入口进入的状态（与后端 RESUMABLE_STATES 对齐）。
RECOVERABLE_STATES: tuple[str, ...] = (
    "init",
    "s1_running",
    "s1_review",
    "s2_running",
    "s2_review",
    "s3_running",
    "s3_review",
    "s4_running",
    "s4_review",
    "iterating",
)

STAGE_PROGRESS: dict[str, int] = {
    "init": 0,
    "s1_running": 15,
    "s1_review": 25,
    "s2_running": 40,
    "s2_review": 50,
    "s3_running": 65,
    "s3_review": 75,
    "s4_running": 88,
    "s4_review": 95,
    "complete": 100,
    "error": 0,
    "recovery_required": 0,
}

MODEL_LABELS: dict[str, str] = {
    "init": "DeepSeek V4 Flash",
    "s1_running": "DeepSeek V4 Pro 🧠",
    "s1_review": "等待确认",
    "s2_running": "DeepSeek V4 Flash",
    "s2_review": "等待确认",
    "s3_running": "DeepSeek V4 Pro 🧠",
    "s3_review": "等待确认",
    "s4_running": "DeepSeek V4 Flash",
    "s4_review": "等待确认",
    "complete": "评估完成",
    "error": "已阻断",
    "recovery_required": "等待恢复",
}

CHAT_PLACEHOLDER: dict[str, str] = {
    "init": "描述你想分析的 AI 模型和应用场景...",
    "s1_running": "补充说明或追问...",
    "s1_review": "输入「确认」继续，或描述你的修改意见...",
    "s2_running": "补充说明或追问...",
    "s2_review": "输入「确认」继续，或描述你的修改意见...",
    "s3_running": "补充说明或追问...",
    "s3_review": "输入「确认」继续，或描述你的修改意见...",
    "s4_running": "补充说明或追问...",
    "s4_review": "输入「确认」完成，或描述你的修改意见...",
    "complete": "评估流程已完成，可从左侧导出报告；上线仍需独立审批。",
    "error": "工作流已阻断，请先恢复会话。",
    "recovery_required": "工作流需人工恢复，请先选择目标状态。",
}
