# tests/test_api_response_contract.py
"""P1 契约回归：关键端点必须声明强类型 response_model。

前端大量依赖这些响应字段的键名；端点一旦退回 `-> dict`，OpenAPI 会退化成
松散对象，字段重命名将静默破坏界面。本测试锁定契约入口。
"""

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


@pytest.fixture(scope="module")
def openapi_schema():
    from api.main import app

    return app.openapi()


def _response_schema(openapi_schema: dict, path: str, method: str) -> dict:
    return openapi_schema["paths"][path][method]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]


def _schema_ref(openapi_schema: dict, path: str, method: str) -> str:
    schema = _response_schema(openapi_schema, path, method)
    if "$ref" in schema:
        return schema["$ref"]
    if "$ref" in schema.get("items", {}):
        return schema["items"]["$ref"]
    if "$ref" in schema.get("additionalProperties", {}):
        return schema["additionalProperties"]["$ref"]
    raise AssertionError(f"{method.upper()} {path} 未声明可解析的 response_model: {schema}")


@pytest.mark.parametrize(
    ("path", "method", "expected"),
    [
        ("/sessions/{session_id}", "get", "ProjectContext"),
        ("/sessions/{session_id}/overview", "get", "SessionOverviewResponse"),
        ("/sessions/{session_id}/actions", "get", "PendingHumanAction"),
        ("/sessions/{session_id}/audit-events", "get", "AuditEvent"),
        ("/sessions/{session_id}/stage-readiness", "get", "StageReadiness"),
        ("/sessions/{session_id}/stage-gate/{stage_id}", "get", "StageGateResult"),
        ("/sessions/{session_id}/stage-resolution", "get", "StageResolutionSummaryResponse"),
        (
            "/sessions/{session_id}/stages/{stage_id}/advancement-decision",
            "get",
            "StageAdvancementDecision",
        ),
        ("/sessions/{session_id}/gate-report", "get", "GateReport"),
        ("/sessions/{session_id}/data-classification", "patch", "UpdateDataClassificationResponse"),
        ("/sessions/{session_id}/stages/{stage_id}/rerun", "post", "StageOperationResultResponse"),
    ],
)
def test_key_endpoints_declare_response_model(openapi_schema, path, method, expected):
    assert _schema_ref(openapi_schema, path, method) == f"#/components/schemas/{expected}"


@pytest.fixture
def isolated_service(tmp_path):
    from core.session_service import SessionService
    from storage.backends.memory_cache import MemoryCache
    from storage.backends.sqlite_store import SQLiteSessionStore

    store = SQLiteSessionStore(str(tmp_path / "workflow.db"))
    store.initialize()
    cache = MemoryCache(ttl_seconds=3600)
    with (
        patch("core.session_service.session_store", store),
        patch("core.session_service.context_cache", cache),
    ):
        yield SessionService()


def test_service_rejects_non_admin_downgrade(isolated_service):
    """降级门槛在 core 层生效，而不是只靠 API 层兜底。"""
    from core.session_service import DataClassificationDowngradeError

    ctx = isolated_service.create_session(tenant_id="test-tenant")
    isolated_service.update_data_classification(
        ctx.session_id,
        data_classification="sensitive_personal",
        note="upgrade",
        actor_role="editor",
        tenant_id="test-tenant",
    )

    with pytest.raises(DataClassificationDowngradeError):
        isolated_service.update_data_classification(
            ctx.session_id,
            data_classification="business_internal",
            note="downgrade attempt",
            actor_role="editor",
            tenant_id="test-tenant",
        )

    reloaded = isolated_service.get_session(ctx.session_id, tenant_id="test-tenant")
    assert reloaded is not None
    assert reloaded.data_classification == "sensitive_personal"


def test_service_allows_admin_downgrade_with_audit(isolated_service):
    ctx = isolated_service.create_session(tenant_id="test-tenant")
    isolated_service.update_data_classification(
        ctx.session_id,
        data_classification="sensitive_personal",
        note="upgrade",
        actor_role="editor",
        tenant_id="test-tenant",
    )

    result = isolated_service.update_data_classification(
        ctx.session_id,
        data_classification="public_demo",
        note="admin downgrade",
        actor_role="admin",
        tenant_id="test-tenant",
    )
    assert result["is_downgrade"] is True
    assert result["after"] == "public_demo"

    reloaded = isolated_service.get_session(ctx.session_id, tenant_id="test-tenant")
    assert reloaded is not None
    assert reloaded.data_classification == "public_demo"
    downgrade_events = [
        event
        for event in reloaded.audit_events
        if event.event_type == "data_classification_changed"
        and event.metadata.get("is_downgrade") is True
    ]
    assert downgrade_events
