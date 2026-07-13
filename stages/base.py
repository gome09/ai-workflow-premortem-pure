# stages/base.py
from __future__ import annotations

import logging
import time
from abc import ABC

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from core.context_manager import get_llm_for_stage_with_context
from core.llm.structured_output import StructuredOutputClient, StructuredOutputResult
from core.models import Message, MessageRole, ProjectContext
from core.traces import append_llm_trace, create_llm_trace
from stages.raw_output_guard import ensure_stage_raw_output
from tools.flag_extractor import extract_flags
from tools.safety_classifier import add_findings_dedup, scan_stage_io

logger = logging.getLogger(__name__)


class BaseStageExecutor(ABC):
    """所有阶段执行器的基类"""

    stage_id: int

    def build_system_prompt(self, ctx: ProjectContext) -> str:
        """子类实现：构建该阶段的 System Prompt"""
        raise NotImplementedError

    def parse_output(self, raw_text: str, ctx: ProjectContext) -> ProjectContext:
        """子类实现：解析 AI 输出，更新 ctx 中对应的结构化字段"""
        raise NotImplementedError

    def parse_structured_output(
        self,
        raw_text: str,
        ctx: ProjectContext,
        *,
        model: str = "",
    ) -> StructuredOutputResult:
        """Run the v0.7 structured-output adapter and remember parser metadata."""
        trace_id = getattr(self, "_active_trace_id", None)
        result = StructuredOutputClient().parse_stage_output(
            self.stage_id,
            raw_text,
            model=model,
            trace_id=trace_id,
        )
        self._last_structured_result = result
        return result

    def run(self, ctx: ProjectContext, user_message: str) -> tuple[str, ProjectContext]:
        """
        执行一轮对话。
        返回：(AI回复文本, 更新后的ctx)
        """
        llm = get_llm_for_stage_with_context(self.stage_id, ctx)
        system_prompt = self.build_system_prompt(ctx)

        # 构建消息列表：system + 历史 + 新消息
        messages = [SystemMessage(content=system_prompt)]
        for msg in ctx.get_stage_history(self.stage_id):
            if msg.role == MessageRole.USER:
                messages.append(HumanMessage(content=msg.content))
            elif msg.role == MessageRole.ASSISTANT:
                messages.append(AIMessage(content=msg.content))

        messages.append(HumanMessage(content=user_message))

        # 调用 LLM and record a v0.7 trace.
        started = time.perf_counter()
        trace = None
        try:
            response = llm.invoke(messages)
            latency_ms = int((time.perf_counter() - started) * 1000)
            ai_text = response.content
            trace = append_llm_trace(
                ctx,
                create_llm_trace(
                    ctx,
                    stage=self.stage_id,
                    node_name=f"stage_{self.stage_id}_executor",
                    model=getattr(llm, "model_name", getattr(llm, "model", "")),
                    prompt_template_id=f"stage_{self.stage_id}_system",
                    latency_ms=latency_ms,
                ),
            )
        except Exception as exc:  # noqa: BLE001 - trace provider failure before surfacing
            latency_ms = int((time.perf_counter() - started) * 1000)
            append_llm_trace(
                ctx,
                create_llm_trace(
                    ctx,
                    stage=self.stage_id,
                    node_name=f"stage_{self.stage_id}_executor",
                    model=getattr(llm, "model_name", getattr(llm, "model", "")),
                    prompt_template_id=f"stage_{self.stage_id}_system",
                    latency_ms=latency_ms,
                    parser_status="not_started",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                ),
            )
            raise

        # 记录对话历史
        ctx.append_message(self.stage_id, Message(role=MessageRole.USER, content=user_message))
        ctx.append_message(self.stage_id, Message(role=MessageRole.ASSISTANT, content=ai_text))

        # 轻量安全扫描：用户输入 + AI 输出
        new_safety_findings = scan_stage_io(
            ctx,
            stage_id=self.stage_id,
            user_message=user_message,
            ai_text=ai_text,
        )
        added_safety_findings = add_findings_dedup(ctx, new_safety_findings)

        # 提取【需核验】项
        new_flags = extract_flags(ai_text, self.stage_id)
        ctx.flagged_items.extend(new_flags)

        # 解析结构化输出（更新 ctx）。解析失败不让整轮崩溃，
        # 而是记录 parser_errors，交给 Review Gate 生成人工 edit 动作。
        try:
            self._active_trace_id = trace.trace_id if trace is not None else None
            self._last_structured_result = None
            ctx = self.parse_output(ai_text, ctx)
            structured_result = getattr(self, "_last_structured_result", None)
            if trace is not None:
                stage_key = f"stage_{self.stage_id}"
                if stage_key in ctx.parser_errors:
                    trace.parser_status = "failed"
                    trace.metadata["parser_error"] = ctx.parser_errors.get(stage_key)
                elif structured_result is not None and structured_result.parser_status != "parsed":
                    trace.parser_status = "markdown_fallback"
                    trace.metadata["structured_parser_status"] = structured_result.parser_status
                    trace.metadata["parser_detail_status"] = structured_result.parser_detail_status
                    trace.metadata["validation_errors"] = structured_result.validation_errors
                    trace.metadata["fallback_used"] = True
                else:
                    trace.parser_status = "parsed"
                    if structured_result is not None:
                        trace.metadata["structured_parser_status"] = structured_result.parser_status
                        trace.metadata["parser_detail_status"] = (
                            structured_result.parser_detail_status
                        )
                        trace.metadata["fallback_used"] = False
        except Exception as exc:  # noqa: BLE001 - 阶段解析失败需要进入人工审核兜底
            ctx = ensure_stage_raw_output(ctx, self.stage_id, ai_text)
            ctx.parser_errors[f"stage_{self.stage_id}"] = str(exc)
            if trace is not None:
                trace.parser_status = "failed"
                trace.error_type = type(exc).__name__
                trace.error_message = str(exc)
            logger.exception("Stage %s parse failed", self.stage_id)
        finally:
            self._active_trace_id = None

        logger.info(
            f"Stage {self.stage_id} round complete. "
            f"Flags extracted: {len(new_flags)}; "
            f"Safety findings added: {added_safety_findings}"
        )
        return ai_text, ctx
