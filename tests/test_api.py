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
pytest.importorskip("prometheus_fastapi_instrumentator")

from fastapi.testclient import TestClient

from core.models import ProjectContext, SessionState
from storage.backends.memory_cache import MemoryCache
from storage.backends.sqlite_store import SQLiteSessionStore


@pytest.fixture
def client():
    """创建测试客户端，Mock 掉存储和图"""
    store = SQLiteSessionStore(":memory:")
    store.initialize()
    cache = MemoryCache(ttl_seconds=3600)
    with (
        patch("storage.session_store.session_store.initialize"),
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
    ):
        from api.main import app

        return TestClient(app)


@pytest.fixture
def mock_session_service():
    with (
        patch("api.routers.session.session_service.create_session") as create_session_mock,
        patch("api.routers.session.session_service.get_session") as get_session_mock,
        patch("api.routers.session.session_service.list_sessions") as list_sessions_mock,
        patch("api.routers.chat.session_service.send_message") as send_message_mock,
    ):
        yield {
            "create_session": create_session_mock,
            "get_session": get_session_mock,
            "list_sessions": list_sessions_mock,
            "send_message": send_message_mock,
        }


class TestSessionAPI:
    def test_create_session(self, client, mock_session_service, auth_headers):
        mock_svc = mock_session_service
        ctx = ProjectContext()
        mock_svc["create_session"].return_value = ctx

        response = client.post("/sessions/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["current_state"] == "init"

    def test_create_session_with_scenario_id(self, client, mock_session_service, auth_headers):
        mock_svc = mock_session_service
        ctx = ProjectContext(selected_scenario_id="university_mental_health")
        mock_svc["create_session"].return_value = ctx

        response = client.post(
            "/sessions/",
            json={"scenario_id": "university_mental_health"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        call_args = mock_svc["create_session"].call_args
        assert call_args.kwargs["scenario_id"] == "university_mental_health"
        assert response.json()["selected_scenario_id"] == "university_mental_health"

    def test_list_builtin_scenarios(self, client, mock_session_service, auth_headers):
        response = client.get("/sessions/scenarios", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert any(item["scenario_id"] == "generic_rag_demo" for item in data)

    def test_get_session_not_found(self, client, mock_session_service, auth_headers):
        mock_svc = mock_session_service
        mock_svc["get_session"].return_value = None

        response = client.get("/sessions/nonexistent-id", headers=auth_headers)
        assert response.status_code == 404

    def test_get_session_success(self, client, mock_session_service, auth_headers):
        mock_svc = mock_session_service
        ctx = ProjectContext()
        ctx.research_target = "GPT-4o"
        mock_svc["get_session"].return_value = ctx

        response = client.get(f"/sessions/{ctx.session_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["research_target"] == "GPT-4o"


class TestChatAPI:
    def test_send_message_success(self, client, mock_session_service, auth_headers):
        mock_chat_svc = mock_session_service["send_message"]
        ctx = ProjectContext()
        ctx.current_state = SessionState.INIT
        mock_chat_svc.return_value = ("AI 回复内容", ctx)

        response = client.post(
            f"/chat/{ctx.session_id}",
            json={"user_input": "我想分析 GPT-4o 在法律领域的失败模式"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ai_reply"] == "AI 回复内容"
        assert data["current_state"] == "init"

    def test_send_message_session_not_found(self, client, mock_session_service, auth_headers):
        mock_chat_svc = mock_session_service["send_message"]
        mock_chat_svc.side_effect = ValueError("Session not found")

        response = client.post(
            "/chat/nonexistent-id",
            json={"user_input": "测试"},
            headers=auth_headers,
        )
        assert response.status_code == 404

    def test_send_message_with_materials(self, client, mock_session_service, auth_headers):
        mock_chat_svc = mock_session_service["send_message"]
        ctx = ProjectContext()
        mock_chat_svc.return_value = ("回复", ctx)

        response = client.post(
            f"/chat/{ctx.session_id}",
            json={
                "user_input": "开始分析",
                "user_materials": ["补充资料内容一", "补充资料内容二"],
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        # 验证 materials 被正确传递
        call_args = mock_chat_svc.call_args
        assert call_args.kwargs["user_materials"] == ["补充资料内容一", "补充资料内容二"]
