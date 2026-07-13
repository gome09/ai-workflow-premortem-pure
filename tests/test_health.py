import os

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-that-is-32-chars-long!!")
os.environ.setdefault("DEEPSEEK_API_KEY", "test")
os.environ.setdefault("TAVILY_API_KEY", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")

from fastapi.testclient import TestClient


def test_health_live_returns_200():
    from api.main import app

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/health/live")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_health_live_no_auth_required():
    """Health endpoint must be accessible without a Bearer token."""
    from api.main import app

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/health/live")
    assert resp.status_code == 200


def test_health_legacy_still_works():
    from api.main import app

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.skip(reason="ready 端点依赖数据库连接，mock 环境下跑不通，后面再补")
def test_health_ready_returns_checks():
    from api.main import app

    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/health/ready")
    assert resp.status_code in (200, 503)
    data = resp.json()
    assert "checks" in data
