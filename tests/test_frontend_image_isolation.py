"""前端镜像隔离契约。

UI 容器被攻破时不得直接触达 PostgreSQL/Redis、不得持有后端密钥，
也不得携带 api/core/graph/stages/storage 源码。本文件把该边界固化为测试。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent

FRONTEND_COMPOSE_FILES = ["docker-compose.yml", "docker-compose.lite.yml"]
ALLOWED_FRONTEND_ENV = {"API_BASE", "DEMO_AUTO_AUTH", "HOME"}


def _compose(name: str) -> dict:
    return yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))


def _env_keys(service: dict) -> set[str]:
    env = service.get("environment") or {}
    if isinstance(env, list):
        return {str(item).split("=", 1)[0] for item in env}
    return set(env)


@pytest.mark.parametrize("compose_file", FRONTEND_COMPOSE_FILES)
def test_frontend_service_receives_no_backend_secrets(compose_file: str):
    service = _compose(compose_file)["services"]["frontend"]
    assert "env_file" not in service, "frontend 不得读取 .env（含数据库凭据与 JWT_SECRET）"
    assert "secrets" not in service, "frontend 不得挂载任何 Docker secret"
    assert _env_keys(service) <= ALLOWED_FRONTEND_ENV
    assert "API_BASE" in _env_keys(service)


@pytest.mark.parametrize("compose_file", FRONTEND_COMPOSE_FILES)
def test_frontend_service_builds_dedicated_image(compose_file: str):
    build = _compose(compose_file)["services"]["frontend"]["build"]
    assert build["dockerfile"] == "Dockerfile.frontend"


def test_frontend_dockerfile_copies_only_frontend_source():
    dockerfile = (ROOT / "Dockerfile.frontend").read_text(encoding="utf-8")
    assert "--only-group frontend" in dockerfile
    assert "COPY frontend/ ./frontend/" in dockerfile
    for forbidden in (
        "COPY . .",
        "COPY api/",
        "COPY core/",
        "COPY graph/",
        "COPY stages/",
        "COPY storage/",
        "COPY auth/",
        "COPY config/",
        "COPY .streamlit/",
        "uvicorn",
        "api.main",
    ):
        assert forbidden not in dockerfile, f"Dockerfile.frontend 不得包含 {forbidden}"


def test_frontend_dependency_group_is_declared():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "[dependency-groups]" in pyproject
    group = pyproject.split("[dependency-groups]", 1)[1].split("[project.urls]", 1)[0]
    for package in ("streamlit", "altair", "pandas", "requests", "python-dotenv"):
        assert package in group, f"frontend 依赖组缺少 {package}"


def test_frontend_source_does_not_import_backend_packages():
    forbidden = ("api", "core", "graph", "stages", "storage", "auth", "tools", "psycopg")
    offenders: list[str] = []
    for path in sorted((ROOT / "frontend").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for module in forbidden:
            if f"\nimport {module}" in text or f"\nfrom {module}" in text:
                offenders.append(f"{path.relative_to(ROOT)} -> {module}")
    assert offenders == []
