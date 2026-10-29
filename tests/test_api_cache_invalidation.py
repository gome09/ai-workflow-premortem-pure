"""P1 回归：429 审计写入后刷新缓存；StaleContextError 返回 409 时失效缓存。"""

from __future__ import annotations

import json

from fastapi.responses import JSONResponse
from starlette.requests import Request

import api.main as api_main
from auth.jwt import create_access_token
from core.models import ProjectContext
from storage.access import SYSTEM_ACCESS
from storage.errors import StaleContextError


def _make_request(headers: dict[str, str] | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "scheme": "http",
        "server": ("testserver", 80),
        "path": "/sessions/s-1/chat",
        "raw_path": b"/sessions/s-1/chat",
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "path_params": {"session_id": "s-1"},
        "client": ("127.0.0.1", 1234),
    }
    return Request(scope)


class _RecordingCache:
    def __init__(self) -> None:
        self.set_ctxs: list[ProjectContext] = []
        self.deleted: list[tuple[str, str]] = []

    def set(self, ctx: ProjectContext) -> None:
        self.set_ctxs.append(ctx)

    def delete(self, session_id: str, tenant_id: str = "") -> None:
        self.deleted.append((session_id, tenant_id))


class _RecordingStore:
    def __init__(self, ctx: ProjectContext | None) -> None:
        self._ctx = ctx
        self.load_calls: list[tuple[str, object]] = []
        self.saved: list[ProjectContext] = []

    def load(self, session_id, tenant_id="", *, system_access=None):
        self.load_calls.append((session_id, system_access))
        return self._ctx

    def save(self, ctx: ProjectContext) -> None:
        self.saved.append(ctx)


class _FakeRateLimit(Exception):
    limit = "10/minute"


def _bearer(tenant_id: str = "tenant-a") -> str:
    token = create_access_token({"sub": "u-1", "tenant_id": tenant_id, "role": "admin"})
    return f"Bearer {token}"


def test_rate_limit_audit_refreshes_cache(monkeypatch) -> None:
    ctx = ProjectContext(session_id="s-1", tenant_id="tenant-a")
    store = _RecordingStore(ctx)
    cache = _RecordingCache()
    monkeypatch.setattr(api_main, "session_store", store)
    monkeypatch.setattr(api_main, "context_cache", cache)
    monkeypatch.setattr(
        api_main,
        "_rate_limit_exceeded_handler",
        lambda request, exc: JSONResponse({"error": "rate limited"}, status_code=429),
    )

    response = api_main._rate_limit_audit_handler(_make_request(), _FakeRateLimit())

    assert response.status_code == 429
    assert store.load_calls == [("s-1", SYSTEM_ACCESS)]
    assert store.saved == [ctx]
    # 审计事件推进了存储版本，缓存必须同步写入，否则后续保存会被误判为陈旧。
    assert cache.set_ctxs == [ctx]
    assert any(event.event_type == "rate_limit_exceeded" for event in ctx.audit_events)


async def test_stale_context_handler_invalidates_cache(monkeypatch) -> None:
    cache = _RecordingCache()
    monkeypatch.setattr(api_main, "context_cache", cache)
    request = _make_request(headers={"Authorization": _bearer()})

    response = await api_main._stale_context_handler(
        request, StaleContextError("s-1", expected_version=2, actual_version=4)
    )

    assert response.status_code == 409
    body = json.loads(response.body)
    assert body["session_id"] == "s-1"
    # reload 必须回源数据库，否则会继续命中旧版本缓存并反复 409。
    assert cache.deleted == [("s-1", "tenant-a")]


async def test_stale_context_handler_without_valid_token_keeps_cache(monkeypatch) -> None:
    cache = _RecordingCache()
    monkeypatch.setattr(api_main, "context_cache", cache)

    for headers in ({}, {"Authorization": "Bearer not-a-token"}):
        response = await api_main._stale_context_handler(
            _make_request(headers=headers),
            StaleContextError("s-1", expected_version=0, actual_version=1),
        )
        assert response.status_code == 409

    assert cache.deleted == []
