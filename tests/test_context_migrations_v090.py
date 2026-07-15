"""T2.1 v0.8.0 → v0.9.0 迁移测试。"""

from core.migrations.registry import CURRENT_CONTEXT_SCHEMA_VERSION
from core.migrations.v080_to_v090 import migrate_v080_to_v090


def _build_v080_fixture() -> dict:
    return {
        "context_schema_version": "0.8.0",
        "session_id": "test-session",
        "research_target": "测试",
        "domain": "测试",
        "user_materials": [],
        "evidence_sources": [],
        "safety_findings": [],
    }


def test_migration_adds_llm_counters():
    raw = _build_v080_fixture()
    migrated = migrate_v080_to_v090(raw)
    assert migrated["llm_call_count"] == 0
    assert migrated["llm_token_estimate"] == 0


def test_migration_bumps_version():
    raw = _build_v080_fixture()
    migrated = migrate_v080_to_v090(raw)
    assert migrated["context_schema_version"] == "0.9.0"


def test_migration_preserves_existing_data():
    raw = _build_v080_fixture()
    raw["research_target"] = "原始研究目标"
    raw["user_materials"] = ["材料 1"]
    migrated = migrate_v080_to_v090(raw)
    assert migrated["research_target"] == "原始研究目标"
    assert migrated["user_materials"] == ["材料 1"]


def test_migration_records_history():
    raw = _build_v080_fixture()
    migrated = migrate_v080_to_v090(raw)
    history = migrated.get("migration_history") or []
    assert any(h["to_version"] == "0.9.0" for h in history)


def test_migration_does_not_overwrite_existing_counters():
    raw = _build_v080_fixture()
    raw["llm_call_count"] = 42  # 已有计数
    migrated = migrate_v080_to_v090(raw)
    assert migrated["llm_call_count"] == 42  # 不覆盖


def test_registry_current_version_is_v0100():
    assert CURRENT_CONTEXT_SCHEMA_VERSION == "0.10.0"
