# tests/test_graph_runner.py
from __future__ import annotations

from unittest.mock import Mock, patch

from core.models import Message, MessageRole, ProjectContext, SessionState
from graph.runner import run_one_step


def test_run_one_step_dispatches_by_current_state():
    ctx = ProjectContext()
    ctx.current_state = SessionState.S1_REVIEW
    ctx.pending_input = "确认"
    mock_node = Mock(side_effect=lambda state, user_input: state)

    with patch.dict("graph.runner.NODE_BY_STATE", {SessionState.S1_REVIEW: mock_node}):
        run_one_step(ctx)

    mock_node.assert_called_once()
    assert mock_node.call_args.args[1] == "确认"
    assert ctx.pending_input == ""


def test_run_one_step_complete_is_noop():
    ctx = ProjectContext()
    ctx.current_state = SessionState.COMPLETE
    ctx.pending_input = "任何输入"

    updated = run_one_step(ctx)

    assert updated is ctx
    assert updated.pending_input == ""


def test_latest_reply_can_be_from_previous_stage():
    from core.session_service import SessionService

    ctx = ProjectContext()
    ctx.current_state = SessionState.S2_RUNNING
    ctx.append_message(1, Message(role=MessageRole.ASSISTANT, content="阶段一确认回复"))

    assert SessionService()._extract_latest_reply(ctx) == "阶段一确认回复"
