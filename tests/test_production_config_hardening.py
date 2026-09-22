from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
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


def test_example_encryption_secrets_are_placeholders_only():
    for name in ("data_encryption_key", "checkpoint_encryption_key"):
        assert (ROOT / "secrets.example" / name).read_text(encoding="utf-8").strip() == "CHANGE_ME"
