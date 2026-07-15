# core/stage3_result_calculator.py
"""Stage 3 overall_passed 确定性计算器。

不信任 fixture 硬编码的 overall_passed 值，而是根据测试结果的
final_pass_status 和 human_review_result 确定性计算。
"""

from __future__ import annotations

from core.models import ProjectContext


def compute_overall_passed(ctx: ProjectContext) -> bool:
    """确定性计算 Stage 3 overall_passed。

    规则：
    1. 无 Stage 3 输出 → False
    2. 无测试结果 → False
    3. 任一 final_pass_status == "failed" → False
    4. 任一 final_pass_status == "pending" → False（未完成不算通过）
    5. 任一 final_pass_status == "blocked" → False
    6. high/critical 风险测试且 human_review_result == "pending" → False
    7. 其余 → True
    """
    if not ctx.stage_3_output:
        return False
    results = ctx.stage_3_output.test_results
    if not results:
        return False

    # 构建 high/critical failure_mode 集合
    high_risk_fm_ids: set[str] = set()
    if ctx.stage_1_output:
        high_risk_fm_ids = {
            fm.id
            for fm in ctx.stage_1_output.failure_modes
            if str(fm.severity).lower() in {"high", "critical"}
        }

    for r in results:
        status = getattr(r, "final_pass_status", "pending")
        if status in ("failed", "pending", "blocked"):
            return False
        # high/critical 风险测试需人工复核
        fm_id = getattr(r, "failure_mode_id", "")
        if fm_id in high_risk_fm_ids:
            review = getattr(r, "human_review_result", "pending")
            if review == "pending":
                return False
    return True


def apply_deterministic_overall_passed(ctx: ProjectContext) -> bool:
    """计算并覆盖 Stage 3 的 overall_passed 字段。

    返回计算后的值。如果 ctx 没有 stage_3_output 则不做操作。
    """
    if not ctx.stage_3_output:
        return False
    computed = compute_overall_passed(ctx)
    ctx.stage_3_output.overall_passed = computed
    return computed
