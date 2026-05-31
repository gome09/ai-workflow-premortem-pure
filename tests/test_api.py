# tests/test_api.py
from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("psycopg")
pytest.importorskip("redis")
pytest.importorskip("langchain_core")
pytest.importorskip("langchain_openai")
pytest.importorskip("tavily")

from fastapi.testclient import TestClient

from core.models import ProjectContext, SessionState


@pytest.fixture
def client():
    """创建测试客户端，Mock 掉存储和图"""
    with patch("storage.session_store.session_store.initialize"):
        from api.main import app

        return TestClient(app)


@pytest.fixture
def mock_session_service():
    with (
        patch("api.routers.session.session_service") as mock,
        patch("api.routers.chat.session_service") as mock_chat,
    ):
        yield mock, mock_chat


class TestSessionAPI:
    def test_create_session(self, client, mock_session_service):
        mock_svc, _ = mock_session_service
        ctx = ProjectContext()
        mock_svc.create_session.return_value = ctx

        response = client.post("/sessions/")
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["current_state"] == "init"

    def test_get_session_not_found(self, client, mock_session_service):
        mock_svc, _ = mock_session_service
        mock_svc.get_session.return_value = None

        response = client.get("/sessions/nonexistent-id")
        assert response.status_code == 404

    def test_get_session_success(self, client, mock_session_service):
        mock_svc, _ = mock_session_service
        ctx = ProjectContext()
        ctx.research_target = "GPT-4o"
        mock_svc.get_session.return_value = ctx

        response = client.get(f"/sessions/{ctx.session_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["research_target"] == "GPT-4o"


class TestChatAPI:
    def test_send_message_success(self, client, mock_session_service):
        _, mock_chat_svc = mock_session_service
        ctx = ProjectContext()
        ctx.current_state = SessionState.INIT
        mock_chat_svc.send_message.return_value = ("AI 回复内容", ctx)

        response = client.post(
            f"/chat/{ctx.session_id}",
            json={"user_input": "我想分析 GPT-4o 在法律领域的失败模式"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ai_reply"] == "AI 回复内容"
        assert data["current_state"] == "init"

    def test_send_message_session_not_found(self, client, mock_session_service):
        _, mock_chat_svc = mock_session_service
        mock_chat_svc.send_message.side_effect = ValueError("Session not found")

        response = client.post(
            "/chat/nonexistent-id",
            json={"user_input": "测试"},
        )
        assert response.status_code == 404

    def test_send_message_with_materials(self, client, mock_session_service):
        _, mock_chat_svc = mock_session_service
        ctx = ProjectContext()
        mock_chat_svc.send_message.return_value = ("回复", ctx)

        response = client.post(
            f"/chat/{ctx.session_id}",
            json={
                "user_input": "开始分析",
                "user_materials": ["补充资料内容一", "补充资料内容二"],
            },
        )
        assert response.status_code == 200
        # 验证 materials 被正确传递
        call_args = mock_chat_svc.send_message.call_args
        assert call_args.kwargs["user_materials"] == ["补充资料内容一", "补充资料内容二"]
