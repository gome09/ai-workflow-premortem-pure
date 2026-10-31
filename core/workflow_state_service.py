# core/workflow_state_service.py
"""工作流状态的确定性安全判定与恢复。

安全不变量：
- 未知 / 非法状态绝不回退到 INIT，而是进入 `RECOVERY_REQUIRED` 并阻断推进。
- `ERROR` / `RECOVERY_REQUIRED` 是显式阻断态：不执行节点、不推进阶段，
  只能通过 `recover_workflow` 显式恢复（写审计）。
- 所有判定只依赖当前状态值，不使用 LLM，不读取外部服务。
"""

from __future__ import annotations

from core.audit_service import append_audit_event
from core.models import ProjectContext, SessionState

BLOCKED_STATES: frozenset[SessionState] = frozenset(
    {SessionState.ERROR, SessionState.RECOVERY_REQUIRED}
)

# 可恢复 / 可推进的正常状态（不含 COMPLETE 与两个阻断态）。
RESUMABLE_STATES: frozenset[SessionState] = frozenset(
    {
        SessionState.INIT,
        SessionState.S1_RUNNING,
        SessionState.S1_REVIEW,
        SessionState.S2_RUNNING,
        SessionState.S2_REVIEW,
        SessionState.S3_RUNNING,
        SessionState.S3_REVIEW,
        SessionState.S4_RUNNING,
        SessionState.S4_REVIEW,
        SessionState.ITERATING,
    }
)


class WorkflowBlockedError(ValueError):
    """Raised when a turn is attempted while the workflow is in a blocked state."""

    def __init__(self, state: str, last_error: str = "", session_id: str = "") -> None:
        self.state = state
        self.last_error = last_error
        self.session_id = session_id
        detail = f"Workflow is blocked in state '{state}'."
        if last_error:
            detail = f"{detail} last_error: {last_error}"
        super().__init__(detail)


def state_value(value: object) -> str:
    """Return the raw string value for an enum or string state."""
    return getattr(value, "value", str(value))


def is_known_state(value: object) -> bool:
    return state_value(value) in {member.value for member in SessionState}


def mark_invalid_state(ctx: ProjectContext, raw_state: object) -> ProjectContext:
    """Fail closed: unknown state becomes RECOVERY_REQUIRED with an audit trail."""
    previous = state_value(ctx.current_state)
    ctx.current_state = SessionState.RECOVERY_REQUIRED
    ctx.last_error = f"invalid workflow state: {raw_state!r}"
    append_audit_event(
        ctx,
        actor="system",
        event_type="workflow_state_invalid",
        target_type="workflow",
        target_id=ctx.session_id,
        before={"current_state": previous},
        after={"current_state": SessionState.RECOVERY_REQUIRED.value},
        metadata={"raw_state": raw_state},
    )
    return ctx


def mark_workflow_error(
    ctx: ProjectContext, reason: str, *, stage: int | None = None
) -> ProjectContext:
    """Fail closed: enter the terminal ERROR state and record the reason."""
    previous = state_value(ctx.current_state)
    ctx.current_state = SessionState.ERROR
    ctx.last_error = reason
    append_audit_event(
        ctx,
        actor="system",
        event_type="workflow_error",
        target_type="workflow",
        target_id=ctx.session_id,
        before={"current_state": previous},
        after={"current_state": SessionState.ERROR.value},
        metadata={"reason": reason, "stage": stage},
    )
    return ctx


def mark_advancement_blocked(ctx: ProjectContext, reason: str) -> ProjectContext:
    """Record that a turn was refused because the workflow is in a blocked state."""
    append_audit_event(
        ctx,
        actor="system",
        event_type="workflow_advancement_blocked",
        target_type="workflow",
        target_id=ctx.session_id,
        after={"current_state": state_value(ctx.current_state)},
        metadata={"reason": reason},
    )
    return ctx


def assert_advanceable(ctx: ProjectContext) -> None:
    """Raise WorkflowBlockedError when the workflow must not advance."""
    state = state_value(ctx.current_state)
    if ctx.current_state in BLOCKED_STATES:
        raise WorkflowBlockedError(state, ctx.last_error or "", ctx.session_id)
    if not is_known_state(ctx.current_state):
        raise WorkflowBlockedError(
            state, ctx.last_error or "unknown workflow state", ctx.session_id
        )


def sanitize_persisted_state(raw: dict) -> dict:
    """Fail closed at the storage boundary: unknown persisted state → RECOVERY_REQUIRED.

    旧版本或人工改库可能留下当前 enum 不认识的 `current_state`。直接交给
    Pydantic 校验会抛 ValidationError（表现为 500/404），调用方既看不到
    阻断原因也无法恢复。这里把它确定性改写为 `RECOVERY_REQUIRED` 并保留原始
    值到 `last_error`，让读取路径依然可解释、可恢复。
    """
    value = raw.get("current_state")
    if value is None or is_known_state(value):
        return raw
    sanitized = dict(raw)
    sanitized["current_state"] = SessionState.RECOVERY_REQUIRED.value
    sanitized["last_error"] = f"invalid persisted workflow state: {value!r}"
    return sanitized


def _resolve_target(target_state: object) -> SessionState:
    try:
        candidate = (
            target_state
            if isinstance(target_state, SessionState)
            else SessionState(str(target_state))
        )
    except ValueError as exc:
        allowed = sorted(member.value for member in RESUMABLE_STATES)
        raise ValueError(f"Unknown target_state {target_state!r}; allowed: {allowed}") from exc
    if candidate not in RESUMABLE_STATES:
        allowed = sorted(member.value for member in RESUMABLE_STATES)
        raise ValueError(f"target_state {candidate.value!r} is not recoverable; allowed: {allowed}")
    return candidate


def recover_workflow(
    ctx: ProjectContext,
    target_state: object,
    *,
    actor: str = "user",
    note: str = "",
) -> ProjectContext:
    """Explicitly leave ERROR / RECOVERY_REQUIRED and return to a resumable state."""
    target = _resolve_target(target_state)
    if ctx.current_state not in BLOCKED_STATES and is_known_state(ctx.current_state):
        raise ValueError(
            f"workflow state {state_value(ctx.current_state)!r} is not blocked; recovery is not allowed"
        )
    before = state_value(ctx.current_state)
    ctx.current_state = target
    ctx.last_error = ""
    append_audit_event(
        ctx,
        actor=actor,
        event_type="workflow_recovered",
        target_type="workflow",
        target_id=ctx.session_id,
        before={"current_state": before},
        after={"current_state": target.value},
        metadata={"note": note},
    )
    return ctx
