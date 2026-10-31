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
    "complete": ("✅", "全流程完成"),
}

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
    "complete": "已完成",
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
    "complete": "全流程已完成，可从左侧导出报告。",
}
