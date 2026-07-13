import os

os.environ.setdefault("JWT_SECRET", "test-secret-key-32-chars-minimum!!")
os.environ.setdefault("DEEPSEEK_API_KEY", "test")
os.environ.setdefault("TAVILY_API_KEY", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")

import pytest
from auth.password import hash_password, verify_password


def test_hash_is_not_plaintext():
    hashed = hash_password("secret123")
    assert hashed != "secret123"
    assert len(hashed) > 20


def test_verify_correct_password():
    hashed = hash_password("mypassword")
    assert verify_password("mypassword", hashed) is True


def test_verify_wrong_password():
    hashed = hash_password("mypassword")
    assert verify_password("wrongpassword", hashed) is False


def test_same_password_produces_different_hashes():
    h1 = hash_password("same")
    h2 = hash_password("same")
    assert h1 != h2


from auth.jwt import create_access_token, create_refresh_token, verify_token
from datetime import timedelta


def test_create_and_verify_access_token():
    token = create_access_token({"sub": "user-123", "tenant_id": "tenant-abc", "role": "member"})
    ctx = verify_token(token)
    assert ctx.user_id == "user-123"
    assert ctx.tenant_id == "tenant-abc"
    assert ctx.role == "member"


def test_expired_token_raises():
    token = create_access_token(
        {"sub": "u", "tenant_id": "t", "role": "member"},
        expires_delta=timedelta(seconds=-1),
    )
    with pytest.raises(Exception):
        verify_token(token)


def test_invalid_token_raises():
    with pytest.raises(Exception):
        verify_token("not.a.valid.token")


def test_access_token_rejected_as_refresh():
    access = create_access_token({"sub": "u", "tenant_id": "t", "role": "member"})
    with pytest.raises(Exception):
        verify_token(access, token_type="refresh")


def test_refresh_token_rejected_as_access():
    refresh = create_refresh_token({"sub": "u", "tenant_id": "t", "role": "member"})
    with pytest.raises(Exception):
        verify_token(refresh, token_type="access")


def test_refresh_token_has_longer_ttl():
    access = create_access_token({"sub": "u", "tenant_id": "t", "role": "member"})
    refresh = create_refresh_token({"sub": "u", "tenant_id": "t", "role": "member"})
    from jose import jwt as jose_jwt

    secret = os.environ["JWT_SECRET"]
    a_payload = jose_jwt.decode(access, secret, algorithms=["HS256"])
    r_payload = jose_jwt.decode(refresh, secret, algorithms=["HS256"])
    assert r_payload["exp"] > a_payload["exp"]


from core.models import ProjectContext


def test_project_context_has_tenant_id():
    ctx = ProjectContext()
    assert hasattr(ctx, "tenant_id")
    assert ctx.tenant_id == ""


def test_project_context_tenant_id_serializes():
    ctx = ProjectContext(tenant_id="t-123")
    data = ctx.model_dump()
    assert data["tenant_id"] == "t-123"


def test_project_context_tenant_id_round_trips_json():
    ctx = ProjectContext(tenant_id="t-abc")
    json_str = ctx.model_dump_json()
    restored = ProjectContext.model_validate_json(json_str)
    assert restored.tenant_id == "t-abc"


from unittest.mock import MagicMock, patch
from storage.cache import ContextCache


def test_cache_key_includes_tenant_id():
    cache = ContextCache.__new__(ContextCache)
    key_t1 = cache._key("sess-1", "tenant-a")
    key_t2 = cache._key("sess-1", "tenant-b")
    assert key_t1 != key_t2
    assert "tenant-a" in key_t1
    assert "tenant-b" in key_t2


def test_cache_set_uses_tenant_id_from_ctx():
    cache = ContextCache.__new__(ContextCache)
    cache._client = MagicMock()
    ctx = ProjectContext(tenant_id="t-xyz", session_id="s-123")
    cache.set(ctx)
    call_args = cache._client.setex.call_args
    assert "t-xyz" in call_args[0][0]
    assert "s-123" in call_args[0][0]


import threading

from storage.session_store import SessionStore


def test_session_store_list_sessions_filters_by_tenant():
    store = SessionStore.__new__(SessionStore)
    store._lock = threading.Lock()
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.execute.return_value.fetchall.return_value = []
    with patch.object(store, "_get_conn", return_value=mock_conn):
        store.list_sessions(limit=10, tenant_id="t-abc")
    sql_call = mock_conn.execute.call_args[0][0]
    assert "tenant_id" in sql_call
    params = mock_conn.execute.call_args[0][1]
    assert "t-abc" in params


def test_session_store_load_filters_by_tenant():
    store = SessionStore.__new__(SessionStore)
    store._lock = threading.Lock()
    mock_conn = MagicMock()
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.execute.return_value.fetchone.return_value = None
    with patch.object(store, "_get_conn", return_value=mock_conn):
        result = store.load("sess-1", "t-abc")
    assert result is None
    sql_call = mock_conn.execute.call_args[0][0]
    assert "tenant_id" in sql_call


from auth.service import AuthService


def _make_service():
    return AuthService()


def test_register_creates_tenant_and_user():
    service = _make_service()
    tenant_row = {"tenant_id": "t-111", "name": "Alice Workspace", "created_at": None}
    user_row = {
        "user_id": "u-222",
        "tenant_id": "t-111",
        "email": "alice@example.com",
        "role": "admin",
        "created_at": None,
    }
    with patch("auth.service.session_store") as mock_store:
        mock_store.get_user_by_email.return_value = None
        mock_store.create_tenant.return_value = tenant_row
        mock_store.create_user.return_value = user_row
        result = service.register(
            "alice@example.com", "password123", workspace_name="Alice Workspace"
        )
    assert result["tenant_id"] == "t-111"
    assert result["user_id"] == "u-222"
    assert "access_token" in result
    assert "refresh_token" in result


def test_login_returns_tokens():
    service = _make_service()
    from auth.password import hash_password

    user_row = {
        "user_id": "u-333",
        "tenant_id": "t-444",
        "email": "bob@example.com",
        "password_hash": hash_password("correctpass"),
        "role": "member",
    }
    with patch("auth.service.session_store") as mock_store:
        mock_store.get_user_by_email.return_value = user_row
        result = service.login("bob@example.com", "correctpass")
    assert "access_token" in result
    assert result["tenant_id"] == "t-444"


def test_login_wrong_password_raises():
    service = _make_service()
    from auth.password import hash_password

    user_row = {
        "user_id": "u-x",
        "tenant_id": "t-x",
        "email": "x@x.com",
        "password_hash": hash_password("realpass"),
        "role": "member",
    }
    with patch("auth.service.session_store") as mock_store:
        mock_store.get_user_by_email.return_value = user_row
        with pytest.raises(Exception):
            service.login("x@x.com", "wrongpass")


def test_login_unknown_email_raises():
    service = _make_service()
    with patch("auth.service.session_store") as mock_store:
        mock_store.get_user_by_email.return_value = None
        with pytest.raises(Exception):
            service.login("nobody@example.com", "pass")


def test_refresh_returns_new_access_token():
    service = _make_service()
    refresh_token = create_refresh_token({"sub": "u-1", "tenant_id": "t-1", "role": "member"})
    result = service.refresh(refresh_token)
    assert "access_token" in result


from fastapi.testclient import TestClient
from fastapi import FastAPI
from auth.router import router as auth_router


def _make_test_app():
    app = FastAPI()
    app.include_router(auth_router)
    return app


def test_register_endpoint_returns_tokens():
    app = _make_test_app()
    client = TestClient(app)
    register_result = {
        "user_id": "u-1",
        "tenant_id": "t-1",
        "email": "test@test.com",
        "access_token": "tok",
        "refresh_token": "ref",
        "token_type": "bearer",
    }
    with patch("auth.router.auth_service.register", return_value=register_result):
        resp = client.post("/auth/register", json={"email": "test@test.com", "password": "pass123"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_endpoint_returns_tokens():
    app = _make_test_app()
    client = TestClient(app)
    login_result = {
        "user_id": "u-1",
        "tenant_id": "t-1",
        "access_token": "tok",
        "refresh_token": "ref",
        "token_type": "bearer",
    }
    with patch("auth.router.auth_service.login", return_value=login_result):
        resp = client.post("/auth/login", data={"username": "test@test.com", "password": "pass"})
    assert resp.status_code == 200


def test_refresh_endpoint():
    app = _make_test_app()
    client = TestClient(app)
    with patch(
        "auth.router.auth_service.refresh",
        return_value={"access_token": "new-tok", "token_type": "bearer"},
    ):
        resp = client.post("/auth/refresh", json={"refresh_token": "old-ref"})
    assert resp.status_code == 200
    assert resp.json()["access_token"] == "new-tok"
