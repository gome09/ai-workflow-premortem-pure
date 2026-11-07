from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from jose import jwt as jose_jwt
from pydantic import ValidationError

from auth.jwt import ALGORITHM, create_access_token
from core.config import Settings, settings

ROOT = Path(__file__).resolve().parent.parent


def _settings(**overrides) -> Settings:
    values = {
        "jwt_secret": "x" * 32,
        "llm_mode": "mock",
        "storage_backend": "sqlite",
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


def _production_settings(**overrides) -> Settings:
    values = {
        "jwt_secret": "x" * 32,
        "llm_mode": "real",
        "deepseek_api_key": "real-key",
        "tavily_api_key": "real-key",
        "storage_backend": "postgres",
        "postgres_password": "db-password",
        "app_env": "production",
        "demo_auto_auth": False,
        "data_encryption_key": Fernet.generate_key().decode(),
        "workflow_execution_mode": "single_step",
        "checkpoint_backend": "postgres",
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("storage_backend", "unknown"),
        ("stage_output_mode", "unknown"),
        ("app_env", "staging"),
        ("model_stage_1_thinking", "sometimes"),
        ("deepseek_reasoning_effort", "medium"),
    ],
)
def test_closed_configuration_fields_reject_unknown_values(field: str, value: str):
    with pytest.raises(ValidationError):
        _settings(**{field: value})


def test_jwt_expiry_uses_settings_single_source(monkeypatch):
    monkeypatch.setattr(settings, "jwt_access_token_expire_minutes", 2)
    token = create_access_token({"sub": "u", "tenant_id": "t", "role": "viewer"})
    payload = jose_jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    remaining = datetime.fromtimestamp(payload["exp"], tz=UTC) - datetime.now(UTC)
    assert 60 < remaining.total_seconds() <= 120


def test_production_compose_disables_demo_auth_and_uses_readiness():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert 'DEMO_AUTO_AUTH: "false"' in compose
    assert "http://localhost:8000/health/ready" in compose
    assert "data_encryption_key" in compose
    assert "checkpoint_encryption_key" in compose


def test_demo_config_explicitly_enables_demo_auth():
    assert "DEMO_AUTO_AUTH=true" in (ROOT / ".env.demo").read_text(encoding="utf-8")


def test_demo_env_file_loads_with_frontend_only_keys():
    """CI 与 make demo-* 会把 .env.demo 复制为 .env；共享 env 文件中的
    DEMO_USER_* 等前端/容器专用键必须被 Settings 忽略，而非导入即失败。
    DEMO_AUTO_AUTH 现在是后端已知开关，仅用于 production 启动拒绝。"""
    loaded = Settings(_env_file=str(ROOT / ".env.demo"))
    assert loaded.demo_auto_auth is True
    assert not hasattr(loaded, "demo_user_email")


def test_valid_production_settings_load():
    loaded = _production_settings()
    assert loaded.app_env == "production"
    assert loaded.demo_auto_auth is False


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("llm_mode", "mock", "LLM_MODE must be real"),
        ("storage_backend", "sqlite", "STORAGE_BACKEND must be postgres"),
        ("demo_auto_auth", True, "DEMO_AUTO_AUTH must be false"),
        ("data_encryption_key", "", "DATA_ENCRYPTION_KEY must be set"),
        ("data_encryption_key", "not-a-fernet-key", "valid Fernet key"),
    ],
)
def test_production_rejects_development_config(field: str, value, message: str):
    with pytest.raises(ValidationError, match=message):
        _production_settings(**{field: value})


def test_example_encryption_secrets_are_placeholders_only():
    for name in ("data_encryption_key", "checkpoint_encryption_key"):
        assert (ROOT / "secrets.example" / name).read_text(encoding="utf-8").strip() == "CHANGE_ME"
