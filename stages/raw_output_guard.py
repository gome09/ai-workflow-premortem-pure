# stages/raw_output_guard.py
from __future__ import annotations

from core.models import (
    ProjectContext,
    Stage1Output,
    Stage2Output,
    Stage3Output,
    Stage4Output,
)


def ensure_stage_raw_output(ctx: ProjectContext, stage_id: int, raw_text: str) -> ProjectContext:
    """Persist raw LLM output even when a stage parser crashes early.

    The report/audit contract requires every LLM response to remain recoverable.
    Stage parsers usually populate raw_summary themselves, but unexpected parser
    exceptions can happen before their fallback branches run. This guard creates
    the minimal stage output object and stores raw_summary in that failure path.
    """
    raw_text = raw_text or ""
    if stage_id == 1:
        if ctx.stage_1_output is None:
            ctx.stage_1_output = Stage1Output(raw_summary=raw_text)
        elif not ctx.stage_1_output.raw_summary:
            ctx.stage_1_output.raw_summary = raw_text
    elif stage_id == 2:
        if ctx.stage_2_output is None:
            ctx.stage_2_output = Stage2Output(raw_summary=raw_text)
        elif not ctx.stage_2_output.raw_summary:
            ctx.stage_2_output.raw_summary = raw_text
    elif stage_id == 3:
        if ctx.stage_3_output is None:
            ctx.stage_3_output = Stage3Output(raw_summary=raw_text)
        elif not ctx.stage_3_output.raw_summary:
            ctx.stage_3_output.raw_summary = raw_text
    elif stage_id == 4:
        if ctx.stage_4_output is None:
            ctx.stage_4_output = Stage4Output(raw_summary=raw_text)
        elif not ctx.stage_4_output.raw_summary:
            ctx.stage_4_output.raw_summary = raw_text
    return ctx
