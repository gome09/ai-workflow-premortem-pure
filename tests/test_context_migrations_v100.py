"""v0.9.0 → v0.10.0 business-closure context migration."""

from __future__ import annotations

from core.migrations import migrate_context
from core.migrations.registry import CURRENT_CONTEXT_SCHEMA_VERSION
from core.migrations.v090_to_v100 import migrate_v090_to_v100


def _build_v090_fixture() -> dict:
    return {
        "context_schema_version": "0.9.0",
        "session_id": "test-session",
        "research_target": "测试",
        "domain": "测试",
        "user_materials": [],
        "evidence_sources": [],
        "safety_findings": [],
    }


def test_migration_adds_closure_collections():
    migrated = migrate_v090_to_v100(_build_v090_fixture())

    assert migrated["risk_treatments"] == []
    assert migrated["project_approvals"] == []


def test_migration_bumps_version_and_records_history():
    migrated = migrate_v090_to_v100(_build_v090_fixture())

    assert migrated["context_schema_version"] == "0.10.0"
    history = migrated.get("migration_history") or []
    assert any(item["from_version"] == "0.9.0" for item in history)
    assert any(item["to_version"] == "0.10.0" for item in history)


def test_migration_preserves_existing_data():
    raw = _build_v090_fixture()
    raw["research_target"] = "原始研究目标"
    migrated = migrate_v090_to_v100(raw)

    assert migrated["research_target"] == "原始研究目标"
    assert raw["context_schema_version"] == "0.9.0"


def test_registry_current_version_is_v100():
    assert CURRENT_CONTEXT_SCHEMA_VERSION == "0.10.0"


def test_full_migration_chain_loads_closure_fields():
    ctx = migrate_context(_build_v090_fixture())

    assert ctx.context_schema_version == "0.10.0"
    assert ctx.risk_treatments == []
    assert ctx.project_approvals == []
