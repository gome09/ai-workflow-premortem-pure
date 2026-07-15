# tests/test_handle_send_message_resync.py
"""回归测试：阶段执行常在同一轮产生多条 assistant 消息（结构化阶段输出 +
审核引导语），但 /chat 的 ai_reply 只带回其中时间戳最新的一条
（core.session_service.SessionService._extract_latest_reply）。

frontend.app.handle_send 若只 append 这一条 ai_reply，结构化阶段输出（例如
阶段二的 workflow_nodes JSON）会静默丢失，不会显示在对话区——即使它已经
正确落盘在服务端 conversation_history 里。

修复方式：handle_send 发送成功后应从服务端权威历史
（get_session + restore_messages_from_ctx）整体重建消息列表，而不是只
append 单条 ai_reply。
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "frontend"))

import app  # noqa: E402


def test_handle_send_surfaces_all_assistant_messages_from_turn(monkeypatch):
    app.st.session_state.clear()
    app.st.session_state["session_id"] = "sess-1"
    app.st.session_state["messages"] = []

    workflow_json = '{"workflow_nodes": [{"node_id": "NODE-MOCK-001"}]}'
    review_guide = "阶段二工作流设计已完成。请审核上方的工作流。"

    fake_ctx = {
        "conversation_history": {
            "stage_2": [
                {"role": "user", "content": "开始"},
                {"role": "assistant", "content": workflow_json},
                {"role": "assistant", "content": review_guide},
            ]
        }
    }

    monkeypatch.setattr(
        app,
        "send_message",
        lambda **kwargs: {"ai_reply": review_guide, "current_state": "s2_review"},
    )
    monkeypatch.setattr(app, "get_session", lambda session_id: fake_ctx)
    monkeypatch.setattr(app, "refresh_flags", lambda: None)
    monkeypatch.setattr(app, "refresh_actions", lambda: None)

    app.handle_send("开始")

    contents = [m["content"] for m in app.st.session_state["messages"]]
    assert workflow_json in contents, (
        "结构化阶段输出消息丢失：handle_send 只展示了 ai_reply 里最新一条消息，"
        f"实际消息列表={contents!r}"
    )
    assert review_guide in contents


def test_handle_send_falls_back_to_ai_reply_when_resync_fails(monkeypatch):
    """服务端重取会话失败时（网络抖动等），至少不能把这轮回复整个丢掉。"""
    app.st.session_state.clear()
    app.st.session_state["session_id"] = "sess-1"
    app.st.session_state["messages"] = []

    monkeypatch.setattr(
        app,
        "send_message",
        lambda **kwargs: {"ai_reply": "fallback reply", "current_state": "s2_review"},
    )
    monkeypatch.setattr(app, "get_session", lambda session_id: None)
    monkeypatch.setattr(app, "refresh_flags", lambda: None)
    monkeypatch.setattr(app, "refresh_actions", lambda: None)

    app.handle_send("开始")

    contents = [m["content"] for m in app.st.session_state["messages"]]
    assert "fallback reply" in contents
