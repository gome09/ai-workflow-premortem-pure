# tests/test_session_service.py
from __future__ import annotations

from unittest.mock import patch

from core.models import Message, MessageRole, ProjectContext
from core.session_service import SessionService


def test_send_message_sets_pending_input_and_runs_one_step():
    service = SessionService()
    ctx = ProjectContext()

    def fake_execute_one_turn(state):
        assert state.pending_input == "真实用户输入"
        state.append_message(0, Message(role=MessageRole.ASSISTANT, content="收到"))
        return state

    with (
        patch.object(service, "get_session", return_value=ctx),
        patch("core.session_service.execute_one_turn", side_effect=fake_execute_one_turn),
        patch("core.session_service.session_store") as mock_store,
        patch("core.session_service.context_cache") as mock_cache,
    ):
        ai_reply, updated_ctx = service.send_message(
            session_id=ctx.session_id,
            user_input="真实用户输入",
            user_materials=["补充资料"],
        )

    assert ai_reply == "收到"
    assert updated_ctx.user_materials == ["补充资料"]
    mock_store.save.assert_called_once_with(updated_ctx)
    mock_cache.set.assert_called_once_with(updated_ctx)
    mock_store.log_event.assert_called_once()
