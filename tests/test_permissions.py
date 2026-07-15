import os

os.environ.setdefault("JWT_SECRET", "test-secret-that-is-32-chars-long!!")
os.environ.setdefault("DEEPSEEK_API_KEY", "test")
os.environ.setdefault("TAVILY_API_KEY", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")

from fastapi import params

from auth.permissions import Role, require_roles


def test_role_values():
    assert Role.viewer == "viewer"
    assert Role.editor == "editor"
    assert Role.admin == "admin"


def test_require_roles_returns_depends():
    dep = require_roles(Role.editor, Role.admin)
    assert isinstance(dep, params.Depends)


def test_role_enum_str():
    assert str(Role.viewer) == "viewer"
    assert Role("admin") == Role.admin
