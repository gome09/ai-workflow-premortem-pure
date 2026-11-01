"""CI must derive the Alembic head dynamically, never hardcode a revision."""

from __future__ import annotations

import re
from pathlib import Path

CI_PATH = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
_HARDCODED_HEAD = re.compile(r"V\d{3}\s*\(head\)")


def test_ci_migration_steps_use_dynamic_head() -> None:
    text = CI_PATH.read_text(encoding="utf-8")

    assert "ScriptDirectory.from_config" in text
    assert "get_current_head()" in text
    assert not _HARDCODED_HEAD.search(text), "CI still hardcodes an Alembic revision as (head)"


def test_repo_alembic_directory_does_not_shadow_installed_package() -> None:
    import alembic

    repo_root = Path(__file__).resolve().parents[1]
    assert not (repo_root / "alembic" / "__init__.py").exists()
    assert Path(alembic.__file__).resolve().parent.parent.name == "site-packages"
