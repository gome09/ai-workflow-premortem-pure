# graph/nodes.py（续，从 _executors 开始）
from __future__ import annotations

import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from core.config import settings
from core.context_manager import (
    build_llm_kwargs_for_stage,
    format_pending_flags,
    parse_review_action,
)
from core.models import Message, MessageRole, ProjectContext, SessionState
from core.oversight_service import bump_stage_output_version
from core.scenario_context import current_domain_profile
from core.stage_advancement_coordinator import advance_stage_if_ready
from core.stage_revision_service import (
    invalidate_downstream_stages,
    record_stage_dependency_versions,
    revise_stage,
    rollback_stage,
)
from graph.review_gate import apply_review_gate
from stages.prompts import get_stage_prompts
from stages.stage_1_failure_mode import Stage1Executor
from stages.stage_2_workflow_design import Stage2Executor
from stages.stage_3_stress_test import Stage3Executor
from stages.stage_4_trigger import Stage4Executor

logger = logging.getLogger(__name__)

# ── 阶段执行器单例 ────────────────────────────────────────────────────────────
_executors = {
    1: Stage1Executor(),
    2: Stage2Executor(),
    3: Stage3Executor(),
    4: Stage4Executor(),
}


# ─────────────────────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────────────────────


def _get_init_llm() -> ChatOpenAI:
    """INIT 阶段使用阶段二模型：DeepSeek V4 Flash + non-thinking，成本较低。"""
    return ChatOpenAI(**build_llm_kwargs_for_stage(0, temperature=0.5, max_tokens=2048))


def _extract_init_fields(profile: str, text: str) -> tuple[str, str, str]:
    normalized = text.replace("**", "")
    if profile == "university_ai":
        target = re.search(r"系统名称[：:]\s*(.+)", normalized)
        domain = re.search(r"应用场景[：:]\s*(.+)", normalized)
        goal = re.search(r"核心目标[：:]\s*(.+)", normalized)
        return (
            target.group(1).strip() if target else "",
            domain.group(1).strip() if domain else "",
            goal.group(1).strip() if goal else "",
        )
    if profile == "medical_ai":
        target = re.search(r"系统名称[：:]\s*(.+)", normalized)
        domain = re.search(r"目标科室/场景[：:]\s*(.+)", normalized)
        goal = re.search(r"核心目标[：:]\s*(.+)", normalized)
        return (
            target.group(1).strip() if target else "",
            domain.group(1).strip() if domain else "",
            goal.group(1).strip() if goal else "",
        )
    target = re.search(r"研究对象[：:]\s*(.+)", normalized)
    domain = re.search(r"具体领域[：:]\s*(.+)", normalized)
    goal = re.search(r"具体目标[：:]\s*(.+)", normalized)
    return (
        target.group(1).strip() if target else "",
        domain.group(1).strip() if domain else "",
        goal.group(1).strip() if goal else "",
    )


def _mock_init_response(profile: str, user_input: str) -> str:
    lines = [line.strip("- ").strip() for line in user_input.splitlines() if line.strip()]
    joined = "\n".join(lines)

    def pick(patterns: list[str], fallback: str) -> str:
        for pattern in patterns:
            match = re.search(pattern, joined)
            if match:
                return match.group(1).strip()
        return fallback

    if profile == "university_ai":
        target = pick([r"系统名称[：:]\s*(.+)"], "高校 AI 应用系统")
        domain = pick([r"应用场景[：:]\s*(.+)", r"场景[：:]\s*(.+)"], "高校教学/管理场景")
        goal = pick([r"核心目标[：:]\s*(.+)"], "支持高校 AI 应用立项评估")
        data = pick([r"涉及数据[：:]\s*(.+)", r"数据[：:]\s*(.+)"], "待补充")
        return (
            "✅ 信息收集完毕，请确认：\n\n"
            f"系统名称：{target}\n"
            f"应用场景：{domain}\n"
            f"核心目标：{goal}\n"
            f"涉及数据：{data}\n\n"
            "确认无误后开始阶段一风险识别，你也可以补充参考资料。"
        )
    if profile == "medical_ai":
        target = pick([r"系统名称[：:]\s*(.+)"], "医疗 AI 系统")
        domain = pick([r"目标科室/场景[：:]\s*(.+)", r"应用场景[：:]\s*(.+)"], "临床应用场景")
        patient = pick([r"患者群体[：:]\s*(.+)"], "待补充")
        decision = pick([r"决策类型[：:]\s*(.+)"], "待补充")
        goal = pick([r"核心目标[：:]\s*(.+)"], "支持医疗 AI 上线前评估")
        return (
            "✅ 信息收集完毕，请确认：\n\n"
            f"系统名称：{target}\n"
            f"目标科室/场景：{domain}\n"
            f"患者群体：{patient}\n"
            f"决策类型：{decision}\n"
            f"核心目标：{goal}\n\n"
            "确认无误后开始阶段一风险识别，你也可以补充参考资料。"
        )
    target = pick([r"研究对象[：:]\s*(.+)"], "AI 项目")
    domain = pick([r"具体领域[：:]\s*(.+)"], "通用业务场景")
    goal = pick([r"具体目标[：:]\s*(.+)"], "完成立项阶段风险分析")
    return (
        "✅ 信息收集完毕，请确认：\n\n"
        f"研究对象：{target}\n"
        f"具体领域：{domain}\n"
        f"具体目标：{goal}\n\n"
        "确认无误后我们将开始阶段一分析，你也可以现在补充任何参考资料。"
    )


def _append_assistant_message(ctx: ProjectContext, stage: int, content: str) -> None:
    ctx.append_message(stage, Message(role=MessageRole.ASSISTANT, content=content))


def _append_user_message(ctx: ProjectContext, stage: int, content: str) -> None:
    ctx.append_message(stage, Message(role=MessageRole.USER, content=content))


# ─────────────────────────────────────────────────────────────────────────────
# 实时人工监督占位标记
#
# 对话区历史消息是「冻结快照」，而左侧面板是「实时重算」。若把待处理动作 / 阻断器
# 的数量与明细写死进历史消息，用户处理后左侧归零、右侧仍显示旧数字，就会出现
# 不同步。为此，审核引导语与被阻断提示只写入一个稳定的单行标记，前端渲染时识别
# 该标记并基于实时数据展开人工监督摘要。
# 标记对 LLM 无害：它是一句自然语言，后续轮次被回放进上下文也不会误导模型。
# ─────────────────────────────────────────────────────────────────────────────

_LIVE_OVERSIGHT_PREFIX = "[[LIVE_OVERSIGHT"


def live_oversight_marker(stage: int) -> str:
    """返回内嵌在助手消息中的实时人工监督占位标记（含 stage 上下文）。"""
    return f"{_LIVE_OVERSIGHT_PREFIX} stage={stage}]]"


def _build_review_prompt(ctx: ProjectContext, stage: int) -> str:
    """构建审核节点的引导文本。

    人工监督事项（待处理动作 / 阶段阻断器）的数量与明细**不再写死**进这条
    消息，而是以 ``LIVE_OVERSIGHT`` 标记占位，由前端在渲染时基于实时的
    pending_actions / stage_readiness 展开。这样对话区永远不会与左侧面板
    出现「右边说 N 项、左边说 0 项」的历史快照漂移。
    """
    pending_count, pending_text = format_pending_flags(ctx)
    template = get_stage_prompts(current_domain_profile(ctx))["review"][stage]

    kwargs = dict(
        pending_flags_count=pending_count,
        pending_flags_text=pending_text,
    )

    # 阶段三额外注入压测结论
    if stage == 3 and ctx.stage_3_output:
        passed = "✅ 通过" if ctx.stage_3_output.overall_passed else "❌ 未通过"
        kwargs["test_conclusion"] = passed

    base_prompt = template.format(**kwargs)
    return f"{base_prompt}\n{live_oversight_marker(stage)}"


# ─────────────────────────────────────────────────────────────────────────────
# LangGraph 节点函数
# 每个节点接收 state(ProjectContext) + user_input，返回更新后的 state
# ─────────────────────────────────────────────────────────────────────────────


def node_init(state: ProjectContext, user_input: str) -> ProjectContext:
    """
    INIT 节点：对话式收集研究对象/领域/目标。
    当检测到用户确认后，提取三要素并推进到阶段一。
    """
    # 用户消息先落盘，LLM 失败时不丢失用户输入
    _append_user_message(state, 0, user_input)

    try:
        profile = current_domain_profile(state)
        if settings.llm_mode == "mock":
            ai_text = _mock_init_response(profile, user_input)
        else:
            llm = _get_init_llm()

            messages = [SystemMessage(content=get_stage_prompts(profile)["init"])]
            for msg in state.get_stage_history(0):
                if msg.role == MessageRole.USER:
                    messages.append(HumanMessage(content=msg.content))
                else:
                    from langchain_core.messages import AIMessage

                    messages.append(AIMessage(content=msg.content))
            messages.append(HumanMessage(content=user_input))

            response = llm.invoke(messages)
            ai_text = response.content
    except Exception as exc:
        err_str = str(exc)
        if "401" in err_str or "authentication" in err_str.lower():
            error_summary = f"LLM authentication failure ({type(exc).__name__})"
        elif (
            "timeout" in err_str.lower()
            or "connect" in err_str.lower()
            or "refused" in err_str.lower()
        ):
            error_summary = f"LLM connection/timeout ({type(exc).__name__})"
        else:
            # Truncate to avoid leaking raw response bodies; keep type for diagnostics
            safe_detail = err_str.split("api key")[0][:120].strip()
            error_summary = f"LLM invocation failure ({type(exc).__name__}): {safe_detail}"

        state.last_error = error_summary
        state.current_state = SessionState.INIT
        logger.error("[%s] node_init LLM error: %s", state.session_id, error_summary)
        return state

    _append_assistant_message(state, 0, ai_text)

    # 检测是否完成信息收集（AI 输出了确认总结格式）
    # Strip markdown bold markers (**) before checking — LLMs often wrap text in bold
    if "✅ 信息收集完毕" in ai_text.replace("**", ""):
        profile = current_domain_profile(state)
        state.research_target, state.domain, state.goal = _extract_init_fields(profile, ai_text)

        # 推进到阶段一
        state.current_state = SessionState.S1_RUNNING
        logger.info(
            f"[{state.session_id}] INIT complete → S1_RUNNING | target={state.research_target}"
        )
    else:
        state.current_state = SessionState.INIT

    return state


def node_stage_running(
    state: ProjectContext,
    user_input: str,
    stage: int,
) -> ProjectContext:
    """
    通用阶段执行节点。
    调用对应阶段的 Executor，执行一轮对话，完成后切换到 REVIEW 状态。
    """
    executor = _executors[stage]
    review_states = {
        1: SessionState.S1_REVIEW,
        2: SessionState.S2_REVIEW,
        3: SessionState.S3_REVIEW,
        4: SessionState.S4_REVIEW,
    }

    try:
        ai_text, state = executor.run(state, user_input)
        stage_output_version = bump_stage_output_version(state, stage)
        record_stage_dependency_versions(state, stage)
        invalidate_downstream_stages(
            state,
            changed_stage=stage,
            reason=f"Stage {stage} regenerated at version {stage_output_version}.",
        )
        state = apply_review_gate(state, stage, stage_output_version=stage_output_version)
        state.current_state = review_states[stage]

        # 追加审核引导语
        review_guide = _build_review_prompt(state, stage)
        _append_assistant_message(state, stage, f"\n\n---\n{review_guide}")

        logger.info(f"[{state.session_id}] Stage {stage} round done → REVIEW")

    except Exception as e:
        state.last_error = str(e)
        logger.error(f"[{state.session_id}] Stage {stage} error: {e}")
        # 保持当前运行状态，让用户可以重试
        state.current_state = {
            1: SessionState.S1_RUNNING,
            2: SessionState.S2_RUNNING,
            3: SessionState.S3_RUNNING,
            4: SessionState.S4_RUNNING,
        }[stage]

    return state


def node_stage_review(
    state: ProjectContext,
    user_input: str,
    stage: int,
) -> ProjectContext:
    """
    通用审核节点。
    解析用户意图，执行路由决策并更新状态。
    """
    action, extra = parse_review_action(user_input)

    _append_user_message(state, stage, user_input)

    if action == "approve":
        decision = advance_stage_if_ready(
            state,
            stage,
            reason="user_review_approve",
            source="graph_review",
        )
        if not decision.advanced:
            _append_assistant_message(
                state,
                stage,
                "🚦 当前阶段暂时不能继续推进。\n"
                f"{live_oversight_marker(stage)}\n\n"
                "请先在左侧「待处理人工动作」面板中逐项处理，"
                "或者输入「修改」/「回退」调整当前阶段。",
            )
            logger.info(
                "[%s] Stage %s approve blocked by StageAdvancementDecision: %s",
                state.session_id,
                stage,
                decision.decision_reason,
            )
            return state

        if state.current_state == SessionState.COMPLETE:
            _append_assistant_message(
                state, stage, "🎉 全流程完成！你可以在左侧面板导出完整分析报告。"
            )
        else:
            next_stage = stage + 1
            _append_assistant_message(
                state,
                stage,
                f"✅ 阶段{stage}已确认，进入阶段{next_stage}。请描述你想要分析的方向，或直接发送「开始」让我自动推进。",
            )
        logger.info(
            "[%s] Stage %s approved through StageAdvancementDecision → %s",
            state.session_id,
            stage,
            state.current_state,
        )

    elif action == "revise":
        revise_stage(
            state,
            stage=stage,
            reason="用户要求修改当前阶段，取消旧的待处理人工动作并标记下游阶段过期。",
            note=extra,
        )

        if state.iteration_count > state.max_iterations:
            _append_assistant_message(
                state,
                stage,
                f"⚠️ 当前阶段已修改 {state.iteration_count} 次。建议你先确认当前版本继续推进，"
                f"或回退上一阶段重新梳理输入。输入「确认」继续，或「回退」返回上一阶段。",
            )
        else:
            _append_assistant_message(
                state, stage, f"收到修改意见，正在基于你的反馈重新生成阶段{stage}内容..."
            )
        logger.info(
            f"[{state.session_id}] Stage {stage} revise → S{stage}_RUNNING "
            f"(iteration {state.iteration_count})"
        )

    elif action == "back":
        rollback_stage(
            state,
            from_stage=stage,
            to_stage=max(stage - 1, 0),
            reason="用户要求回退，取消当前阶段旧的待处理人工动作并标记下游阶段过期。",
        )
        _append_assistant_message(
            state, stage, f"已回退到阶段{stage - 1}，你可以修改之前的内容后重新推进。"
        )
        logger.info(f"[{state.session_id}] Stage {stage} back → {state.current_state}")

    elif action == "back_to_design" and stage == 3:
        rollback_stage(
            state,
            from_stage=3,
            to_stage=2,
            reason="用户要求回退到工作流设计，阶段三及下游输出标记为过期。",
            target_running=True,
        )
        _append_assistant_message(
            state, stage, "已回退到阶段二工作流设计，请描述你希望如何调整工作流。"
        )
        logger.info(f"[{state.session_id}] Stage 3 back_to_design → S2_RUNNING")

    else:
        # 无法识别意图，引导用户
        _append_assistant_message(
            state,
            stage,
            "我没有理解你的意图，请输入：\n"
            "- **确认** → 进入下一阶段\n"
            "- **修改 + 具体意见** → 重新生成\n"
            "- **回退** → 返回上一阶段",
        )

    return state


# ── 具体节点函数（供 LangGraph 注册）────────────────────────────────────────


def node_s1_running(state: ProjectContext, user_input: str) -> ProjectContext:
    return node_stage_running(state, user_input, stage=1)


def node_s1_review(state: ProjectContext, user_input: str) -> ProjectContext:
    return node_stage_review(state, user_input, stage=1)


def node_s2_running(state: ProjectContext, user_input: str) -> ProjectContext:
    return node_stage_running(state, user_input, stage=2)


def node_s2_review(state: ProjectContext, user_input: str) -> ProjectContext:
    return node_stage_review(state, user_input, stage=2)


def node_s3_running(state: ProjectContext, user_input: str) -> ProjectContext:
    return node_stage_running(state, user_input, stage=3)


def node_s3_review(state: ProjectContext, user_input: str) -> ProjectContext:
    return node_stage_review(state, user_input, stage=3)


def node_s4_running(state: ProjectContext, user_input: str) -> ProjectContext:
    return node_stage_running(state, user_input, stage=4)


def node_s4_review(state: ProjectContext, user_input: str) -> ProjectContext:
    return node_stage_review(state, user_input, stage=4)
