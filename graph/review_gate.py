# graph/review_gate.py
from __future__ import annotations

import logging

from core.models import ProjectContext
from core.oversight_service import create_review_actions_for_stage
from tools.safety_classifier import add_findings_dedup, scan_policy_gaps

logger = logging.getLogger(__name__)


def apply_review_gate(
    ctx: ProjectContext,
    stage: int,
    *,
    stage_output_version: int | None = None,
) -> ProjectContext:
    """
    阶段 executor 完成后统一进入 Review Gate。
    当前 gate 创建正式人工动作，并将动作绑定到阶段输出版本。
    """
    add_findings_dedup(ctx, scan_policy_gaps(ctx, stage_id=stage))
    created = create_review_actions_for_stage(
        ctx,
        stage,
        stage_output_version=stage_output_version,
    )
    if created:
        logger.info(
            "[%s] Review gate created %s human action(s) for stage %s v%s",
            ctx.session_id,
            len(created),
            stage,
            stage_output_version,
        )
    return ctx
