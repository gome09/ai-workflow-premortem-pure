# tests/test_governance_api_v110.py
"""T3.4 组织级治理聚合 API 契约测试。

覆盖：
- 三个只读端点 GET /governance/overview、/gate-trends、/actions-backlog 返回 200
- 未认证请求返回 401
- viewer 角色可读（治理透明度）
- tenant 隔离：用 tenant A 的 token 调用，数据只含 A 的会话
- overview 结构含 sessions_total/state_distribution/risk_tier_distribution/
  open_safety_findings/pending_actions/reports_exported 键
- gate-trends 默认 8 周，可传 weeks 参数
- 聚合数值正确：插入 3 个会话（不同状态）→ overview.sessions_total == 3
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from unittest.mock import patch

os.environ.setdefault("STORAGE_BACKEND", "sqlite")

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("redis")

from fastapi.testclient import TestClient

from auth.jwt import create_access_token
from storage.backends.sqlite_store import SQLiteSessionStore

# ─────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────


@pytest.fixture
def governance_store(tmp_path):
    """Fresh isolated SQLite store for governance API tests."""
    db_path = str(tmp_path / "test_governance_api.db")
    store = SQLiteSessionStore(db_path=db_path)
    store.initialize()
    return store


@pytest.fixture
def client(governance_store):
    """TestClient with governance router's session_store patched to test store.

    Uses yield so the patch stays active during test execution (the governance
    router looks up ``session_store`` at request time via its module global).
    """
    with patch("api.routers.governance.session_store", governance_store):
        from api.main import app

        yield TestClient(app)


def _auth_headers(tenant_id: str = "test-tenant", role: str = "admin") -> dict:
    token = create_access_token({"sub": "test-user", "tenant_id": tenant_id, "role": role})
    return {"Authorization": f"Bearer {token}"}


# ─────────────────────────────────────────────────────────
# Helpers — direct SQL insertion (same pattern as test_gate_evaluation_records_v110)
# ─────────────────────────────────────────────────────────


def _insert_session(
    store,
    *,
    session_id: str,
    tenant_id: str,
    current_state: str,
    context_json: dict,
) -> None:
    with store._get_conn() as conn:
        conn.execute(
            "INSERT INTO sessions "
            "(session_id, tenant_id, current_state, context_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                session_id,
                tenant_id,
                current_state,
                json.dumps(context_json),
                "2026-07-14T00:00:00",
                "2026-07-14T00:00:00",
            ),
        )
        conn.commit()


def _insert_eval(
    store,
    *,
    session_id: str,
    tenant_id: str,
    stage_id: int,
    risk_tier: str,
    passed: bool,
    blocking_rule_ids: list,
    evaluated_at: str,
) -> None:
    record_id = str(uuid.uuid4())[:8]
    with store._get_conn() as conn:
        conn.execute(
            "INSERT INTO gate_evaluation_records "
            "(record_id, session_id, tenant_id, stage_id, risk_tier, passed, "
            " blocking_rule_ids, rule_versions, evaluated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record_id,
                session_id,
                tenant_id,
                stage_id,
                risk_tier,
                int(passed),
                json.dumps(blocking_rule_ids),
                json.dumps({}),
                evaluated_at,
            ),
        )
        conn.commit()


# ─────────────────────────────────────────────────────────
# 1. /governance/overview
# ─────────────────────────────────────────────────────────


class TestGovernanceOverviewEndpoint:
    def test_returns_200_with_auth(self, client, auth_headers):
        resp = client.get("/governance/overview", headers=auth_headers)
        assert resp.status_code == 200

    def test_returns_401_without_auth(self, client):
        resp = client.get("/governance/overview")
        assert resp.status_code == 401

    def test_viewer_can_read(self, client):
        """治理透明度：viewer 角色可读治理总览。"""
        headers = _auth_headers(role="viewer")
        resp = client.get("/governance/overview", headers=headers)
        assert resp.status_code == 200

    def test_overview_structure(self, client, auth_headers):
        resp = client.get("/governance/overview", headers=auth_headers)
        data = resp.json()
        expected_keys = {
            "sessions_total",
            "state_distribution",
            "risk_tier_distribution",
            "open_safety_findings",
            "pending_actions",
            "reports_exported",
        }
        assert set(data.keys()) == expected_keys

    def test_aggregation_correctness(self, client, governance_store, auth_headers):
        """插入 3 个会话（不同状态）→ overview.sessions_total == 3。"""
        _insert_session(
            governance_store,
            session_id="s1",
            tenant_id="test-tenant",
            current_state="s1_running",
            context_json={},
        )
        _insert_session(
            governance_store,
            session_id="s2",
            tenant_id="test-tenant",
            current_state="complete",
            context_json={},
        )
        _insert_session(
            governance_store,
            session_id="s3",
            tenant_id="test-tenant",
            current_state="s2_running",
            context_json={},
        )

        resp = client.get("/governance/overview", headers=auth_headers)
        data = resp.json()
        assert data["sessions_total"] == 3
        assert data["state_distribution"]["s1_running"] == 1
        assert data["state_distribution"]["complete"] == 1
        assert data["state_distribution"]["s2_running"] == 1

    def test_empty_tenant_returns_zeros(self, client, auth_headers):
        resp = client.get("/governance/overview", headers=auth_headers)
        data = resp.json()
        assert data["sessions_total"] == 0
        assert data["state_distribution"] == {}
        assert data["risk_tier_distribution"] == {}
        assert data["open_safety_findings"] == 0
        assert data["pending_actions"] == 0
        assert data["reports_exported"] == 0


# ─────────────────────────────────────────────────────────
# 2. /governance/gate-trends
# ─────────────────────────────────────────────────────────


class TestGateTrendsEndpoint:
    def test_returns_200_with_auth(self, client, auth_headers):
        resp = client.get("/governance/gate-trends", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_returns_401_without_auth(self, client):
        resp = client.get("/governance/gate-trends")
        assert resp.status_code == 401

    def test_viewer_can_read(self, client):
        headers = _auth_headers(role="viewer")
        resp = client.get("/governance/gate-trends", headers=headers)
        assert resp.status_code == 200

    def test_default_8_weeks(self, client, auth_headers):
        """默认 weeks=8，返回 list。"""
        resp = client.get("/governance/gate-trends", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_accepts_weeks_param(self, client, auth_headers):
        resp = client.get("/governance/gate-trends?weeks=4", headers=auth_headers)
        assert resp.status_code == 200

    def test_weeks_validation_ge1(self, client, auth_headers):
        resp = client.get("/governance/gate-trends?weeks=0", headers=auth_headers)
        assert resp.status_code == 422

    def test_weeks_validation_le52(self, client, auth_headers):
        resp = client.get("/governance/gate-trends?weeks=53", headers=auth_headers)
        assert resp.status_code == 422

    def test_trends_aggregation(self, client, governance_store, auth_headers):
        """插入评估记录后，趋势正确聚合。"""
        now = datetime.utcnow()
        _insert_eval(
            governance_store,
            session_id="gt1",
            tenant_id="test-tenant",
            stage_id=1,
            risk_tier="medium",
            passed=True,
            blocking_rule_ids=[],
            evaluated_at=now.isoformat(),
        )
        _insert_eval(
            governance_store,
            session_id="gt2",
            tenant_id="test-tenant",
            stage_id=1,
            risk_tier="high",
            passed=False,
            blocking_rule_ids=["missing_output"],
            evaluated_at=now.isoformat(),
        )

        resp = client.get("/governance/gate-trends", headers=auth_headers)
        data = resp.json()
        assert len(data) >= 1
        total_evals = sum(b["evaluations"] for b in data)
        assert total_evals == 2
        total_passed = sum(b["passed"] for b in data)
        assert total_passed == 1


# ─────────────────────────────────────────────────────────
# 3. /governance/actions-backlog
# ─────────────────────────────────────────────────────────


class TestActionsBacklogEndpoint:
    def test_returns_200_with_auth(self, client, auth_headers):
        resp = client.get("/governance/actions-backlog", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_returns_401_without_auth(self, client):
        resp = client.get("/governance/actions-backlog")
        assert resp.status_code == 401

    def test_viewer_can_read(self, client):
        headers = _auth_headers(role="viewer")
        resp = client.get("/governance/actions-backlog", headers=headers)
        assert resp.status_code == 200

    def test_accepts_limit_param(self, client, auth_headers):
        resp = client.get("/governance/actions-backlog?limit=10", headers=auth_headers)
        assert resp.status_code == 200

    def test_limit_validation_ge1(self, client, auth_headers):
        resp = client.get("/governance/actions-backlog?limit=0", headers=auth_headers)
        assert resp.status_code == 422

    def test_limit_validation_le200(self, client, auth_headers):
        resp = client.get("/governance/actions-backlog?limit=201", headers=auth_headers)
        assert resp.status_code == 422

    def test_backlog_aggregation(self, client, governance_store, auth_headers):
        """插入待处理动作后，积压列表正确返回。"""
        _insert_session(
            governance_store,
            session_id="ab1",
            tenant_id="test-tenant",
            current_state="s1_running",
            context_json={
                "pending_actions": [
                    {
                        "action_id": "act-1",
                        "title": "核验证据",
                        "risk_level": "high",
                        "status": "pending",
                        "stage_id": 1,
                        "created_at": "2026-07-10T00:00:00",
                    }
                ]
            },
        )

        resp = client.get("/governance/actions-backlog", headers=auth_headers)
        data = resp.json()
        assert len(data) == 1
        assert data[0]["action_id"] == "act-1"
        assert data[0]["risk_level"] == "high"


# ─────────────────────────────────────────────────────────
# 4. tenant 隔离
# ─────────────────────────────────────────────────────────


class TestTenantIsolation:
    def test_overview_tenant_isolation(self, client, governance_store):
        """用 tenant A 的 token 调用，数据只含 A 的会话。"""
        _insert_session(
            governance_store,
            session_id="ta-gov",
            tenant_id="tenantA",
            current_state="init",
            context_json={},
        )
        _insert_session(
            governance_store,
            session_id="tb-gov",
            tenant_id="tenantB",
            current_state="init",
            context_json={},
        )

        resp_a = client.get("/governance/overview", headers=_auth_headers(tenant_id="tenantA"))
        assert resp_a.status_code == 200
        data_a = resp_a.json()
        assert data_a["sessions_total"] == 1

        resp_b = client.get("/governance/overview", headers=_auth_headers(tenant_id="tenantB"))
        assert resp_b.status_code == 200
        data_b = resp_b.json()
        assert data_b["sessions_total"] == 1

    def test_gate_trends_tenant_isolation(self, client, governance_store):
        now = datetime.utcnow().isoformat()
        _insert_eval(
            governance_store,
            session_id="ta-trend",
            tenant_id="tenantA",
            stage_id=1,
            risk_tier="medium",
            passed=True,
            blocking_rule_ids=[],
            evaluated_at=now,
        )
        _insert_eval(
            governance_store,
            session_id="tb-trend",
            tenant_id="tenantB",
            stage_id=1,
            risk_tier="high",
            passed=False,
            blocking_rule_ids=["missing_output"],
            evaluated_at=now,
        )

        trends_a = client.get(
            "/governance/gate-trends", headers=_auth_headers(tenant_id="tenantA")
        ).json()
        total_a = sum(b["evaluations"] for b in trends_a)
        assert total_a == 1
        assert all(b["passed"] == 1 for b in trends_a)

        trends_b = client.get(
            "/governance/gate-trends", headers=_auth_headers(tenant_id="tenantB")
        ).json()
        total_b = sum(b["evaluations"] for b in trends_b)
        assert total_b == 1
        assert all(b["passed"] == 0 for b in trends_b)

    def test_actions_backlog_tenant_isolation(self, client, governance_store):
        _insert_session(
            governance_store,
            session_id="ta-act",
            tenant_id="tenantA",
            current_state="init",
            context_json={
                "pending_actions": [
                    {
                        "action_id": "a-ta",
                        "title": "TA action",
                        "risk_level": "high",
                        "status": "pending",
                        "stage_id": 1,
                        "created_at": "2026-07-10T00:00:00",
                    }
                ]
            },
        )
        _insert_session(
            governance_store,
            session_id="tb-act",
            tenant_id="tenantB",
            current_state="init",
            context_json={
                "pending_actions": [
                    {
                        "action_id": "a-tb",
                        "title": "TB action",
                        "risk_level": "high",
                        "status": "pending",
                        "stage_id": 1,
                        "created_at": "2026-07-10T00:00:00",
                    }
                ]
            },
        )

        backlog_a = client.get(
            "/governance/actions-backlog", headers=_auth_headers(tenant_id="tenantA")
        ).json()
        assert len(backlog_a) == 1
        assert backlog_a[0]["action_id"] == "a-ta"

        backlog_b = client.get(
            "/governance/actions-backlog", headers=_auth_headers(tenant_id="tenantB")
        ).json()
        assert len(backlog_b) == 1
        assert backlog_b[0]["action_id"] == "a-tb"
