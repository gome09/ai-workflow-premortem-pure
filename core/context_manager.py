# core/context_manager.py
from __future__ import annotations

from typing import Any

from langchain_openai import ChatOpenAI

from core.config import settings
from core.models import ProjectContext


def get_model_name_for_stage(stage: int) -> str:
    """Return the configured DeepSeek model for a workflow stage."""
    model_map = {
        0: settings.model_stage_2,  # INIT 阶段沿用结构化生成模型
        1: settings.model_stage_1,  # V4 Pro + thinking
        2: settings.model_stage_2,  # V4 Flash + non-thinking
        3: settings.model_stage_3,  # V4 Pro + thinking
        4: settings.model_stage_4,  # V4 Flash + non-thinking
    }
    return model_map.get(stage, settings.model_stage_2)


def _normalize_thinking_mode(value: str) -> str | None:
    """Normalize env/config values into DeepSeek V4 thinking mode values."""
    normalized = (value or "default").strip().lower().replace("_", "-")
    if normalized in {"enabled", "enable", "on", "true", "yes", "thinking"}:
        return "enabled"
    if normalized in {"disabled", "disable", "off", "false", "no", "non-thinking"}:
        return "disabled"
    return None


def get_thinking_mode_for_stage(stage: int) -> str | None:
    """Return DeepSeek V4 thinking mode for a workflow stage.

    None means no explicit thinking payload is sent, allowing provider defaults.
    """
    thinking_map = {
        0: settings.model_stage_2_thinking,
        1: settings.model_stage_1_thinking,
        2: settings.model_stage_2_thinking,
        3: settings.model_stage_3_thinking,
        4: settings.model_stage_4_thinking,
    }
    return _normalize_thinking_mode(thinking_map.get(stage, settings.model_stage_2_thinking))


def build_llm_kwargs_for_stage(
    stage: int,
    *,
    temperature: float = 0.3,
    max_tokens: int = 8192,
) -> dict[str, Any]:
    """Build ChatOpenAI kwargs for DeepSeek V4-compatible calls.

    DeepSeek V4 exposes thinking / non-thinking as request-level parameters.
    Thinking mode does not use sampling params such as temperature, so this helper
    only sends temperature when thinking is disabled or left to provider default.
    """
    thinking_mode = get_thinking_mode_for_stage(stage)
    kwargs: dict[str, Any] = {
        "model": get_model_name_for_stage(stage),
        "api_key": settings.deepseek_api_key,
        "base_url": settings.deepseek_base_url,
        "max_tokens": max_tokens,
    }

    if thinking_mode is not None:
        kwargs["extra_body"] = {"thinking": {"type": thinking_mode}}
        if thinking_mode == "enabled":
            kwargs["reasoning_effort"] = settings.deepseek_reasoning_effort
        else:
            kwargs["temperature"] = temperature
    else:
        kwargs["temperature"] = temperature

    return kwargs


def get_llm_for_stage(stage: int) -> ChatOpenAI:
    """
    根据阶段返回对应模型。
    阶段一、三：DeepSeek V4 Pro + thinking，用于深度推理。
    阶段二、四：DeepSeek V4 Flash + non-thinking，用于结构化生成。
    """
    return ChatOpenAI(**build_llm_kwargs_for_stage(stage))


def build_stage_context_injection(ctx: ProjectContext, current_stage: int) -> str:
    """
    构建注入当前阶段 System Prompt 的上下文摘要。
    只传结构化输出，不重放原始对话，防止 token 膨胀。
    """
    # 只注入当前阶段之前的内容
    if current_stage <= 1:
        return ""  # 阶段一是起点，没有前序输出
    return ctx.to_context_summary()


def format_failure_modes_for_prompt(ctx: ProjectContext) -> str:
    """将阶段一输出格式化为阶段二可用的文本"""
    if not ctx.stage_1_output:
        return "（阶段一输出缺失）"
    lines = []
    for fm in ctx.stage_1_output.failure_modes:
        lines.append(f"- [{fm.id}] [{fm.severity.upper()}] {fm.category}：{fm.description}")
    return "\n".join(lines)


def format_workflow_nodes_for_prompt(ctx: ProjectContext) -> str:
    """将阶段二输出格式化为阶段三/四可用的文本"""
    if not ctx.stage_2_output:
        return "（阶段二输出缺失）"
    lines = []
    for node in ctx.stage_2_output.workflow_nodes:
        lines.append(
            f"- [{node.node_id}] {node.stage_name} | "
            f"模型：{node.model_assigned} | "
            f"人工动作：{node.human_action}"
        )
    return "\n".join(lines)


def format_pending_flags(ctx: ProjectContext) -> tuple[int, str]:
    """格式化待处理的【需核验】项，用于审核节点展示"""
    pending = ctx.get_pending_flags()
    if not pending:
        return 0, "（无待处理项）"
    lines = []
    for f in pending:
        lines.append(f"  - [阶段{f.stage}] {f.content}")
    return len(pending), "\n".join(lines)


def parse_review_action(user_input: str) -> tuple[str, str]:
    """
    解析用户在审核节点的输入意图。
    返回：(action, extra_content)
    action: 'approve' | 'revise' | 'back' | 'back_to_design' | 'unknown'
    """
    text = user_input.strip().lower()

    approve_keywords = {"确认", "approve", "ok", "好", "没问题", "通过", "继续"}
    revise_keywords = {"修改", "revise", "修正", "重新", "不对", "有问题"}
    back_keywords = {"回退", "back", "返回", "上一步"}
    back_design_keywords = {"回退工作流", "回到工作流", "back_to_design", "修改工作流"}

    for kw in back_design_keywords:
        if kw in text:
            return "back_to_design", user_input

    for kw in back_keywords:
        if kw in text:
            return "back", user_input

    for kw in approve_keywords:
        if kw in text and len(text) < 20:  # 短文本才认定为纯确认
            return "approve", ""

    for kw in revise_keywords:
        if kw in text:
            return "revise", user_input

    # 默认：用户输入了实质内容，视为修改意见
    if len(user_input.strip()) > 10:
        return "revise", user_input

    return "unknown", user_input
