"""Historical plaintext `goal` backfill for SQLite and shared transform semantics."""

from __future__ import annotations

import json

import pytest
from cryptography.fernet import Fernet

from core.config import settings
from storage.backends.sqlite_store import SQLiteSessionStore
from storage.field_security import _reset_fernet_cache

_KEY = Fernet.generate_key().decode()
_TENANT = "tenant-goal"


@pytest.fixture(autouse=True)
def _reset_encryption_cache():
    _reset_fernet_cache()
    yield
    _reset_fernet_cache()


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_encryption_key", _KEY)
    backend = SQLiteSessionStore(str(tmp_path / "goal_backfill.db"))
    backend.initialize()
    return backend


def _insert_legacy_row(
    store: SQLiteSessionStore,
    *,
    session_id: str,
    goal: str,
    classification: str = "business_internal",
    tenant_id: str = _TENANT,
) -> None:
    context = {
        "context_schema_version": "0.10.0",
        "session_id": session_id,
        "tenant_id": tenant_id,
        "goal": goal,
        "data_classification": classification,
        "current_state": "init",
    }
    with store._get_conn() as conn:  # noqa: SLF001  # direct legacy-row insertion for the test
        conn.execute(
            "INSERT INTO sessions "
            "(session_id, current_state, context_json, tenant_id, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?)",
            (
                session_id,
                "init",
                json.dumps(context, ensure_ascii=False),
                tenant_id,
                "2026-01-01T00:00:00",
                "2026-01-01T00:00:00",
            ),
        )
        conn.commit()


def _raw_context(store: SQLiteSessionStore, session_id: str) -> str:
    with store._get_conn() as conn:  # noqa: SLF001
        row = conn.execute(
            "SELECT context_json FROM sessions WHERE session_id=?", (session_id,)
        ).fetchone()
    assert row is not None
    return row["context_json"]


def test_dry_run_then_apply_encrypts_legacy_goal_and_is_idempotent(store):
    _insert_legacy_row(store, session_id="s-legacy", goal="历史明文目标")

    dry = store.backfill_goal_encryption(dry_run=True)
    assert dry["mode"] == "encrypt"
    assert dry["scanned"] == 1
    assert dry["changed"] == 1
    assert dry["status_counts"] == {"encrypted": 1}
    assert "历史明文目标" in _raw_context(store, "s-legacy")

    applied = store.backfill_goal_encryption(dry_run=False)
    assert applied["changed"] == 1
    raw = _raw_context(store, "s-legacy")
    assert "enc:v1:" in raw
    assert "历史明文目标" not in raw

    loaded = store.load("s-legacy", _TENANT)
    assert loaded is not None
    assert loaded.goal == "历史明文目标"

    again = store.backfill_goal_encryption(dry_run=False)
    assert again["changed"] == 0
    assert again["status_counts"] == {"already_encrypted": 1}


def test_public_demo_is_skipped(store):
    _insert_legacy_row(
        store,
        session_id="s-demo",
        goal="演示目标明文",
        classification="public_demo",
    )

    result = store.backfill_goal_encryption(dry_run=False)

    assert result["status_counts"] == {"public_demo": 1}
    assert "演示目标明文" in _raw_context(store, "s-demo")


def test_verify_and_decrypt_modes(store):
    _insert_legacy_row(store, session_id="s-verify", goal="可验证目标")
    store.backfill_goal_encryption(dry_run=False)

    verified = store.backfill_goal_encryption(verify_only=True)
    assert verified["status_counts"] == {"verified": 1}
    assert verified["changed"] == 0

    decrypted = store.backfill_goal_encryption(decrypt=True, dry_run=False)
    assert decrypted["status_counts"] == {"decrypted": 1}
    assert decrypted["changed"] == 1
    assert "可验证目标" in _raw_context(store, "s-verify")


def test_session_filter_limits_sweep(store):
    _insert_legacy_row(store, session_id="s-a", goal="目标 A")
    _insert_legacy_row(store, session_id="s-b", goal="目标 B")

    result = store.backfill_goal_encryption(dry_run=False, session_ids=["s-a"])

    assert result["scanned"] == 1
    assert result["changed"] == 1
    assert "enc:v1:" in _raw_context(store, "s-a")
    assert "目标 B" in _raw_context(store, "s-b")


def test_missing_key_refuses_to_write(store, monkeypatch):
    _insert_legacy_row(store, session_id="s-nokey", goal="无密钥目标")
    monkeypatch.setattr(settings, "data_encryption_key", "")
    _reset_fernet_cache()

    with pytest.raises(RuntimeError, match="DATA_ENCRYPTION_KEY"):
        store.backfill_goal_encryption(dry_run=False)

    assert "无密钥目标" in _raw_context(store, "s-nokey")


def test_invalid_json_is_reported_without_aborting(store):
    with store._get_conn() as conn:  # noqa: SLF001
        conn.execute(
            "INSERT INTO sessions "
            "(session_id, current_state, context_json, tenant_id, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?)",
            ("s-bad", "init", "{not-json", _TENANT, "2026-01-01", "2026-01-01"),
        )
        conn.commit()

    result = store.backfill_goal_encryption(dry_run=False)

    assert result["scanned"] == 1
    assert result["status_counts"] == {"invalid_json": 1}
    assert result["changed"] == 0


def test_dry_run_and_apply_counts_are_consistent(store):
    _insert_legacy_row(store, session_id="s-a", goal="目标 A")
    _insert_legacy_row(store, session_id="s-b", goal="目标 B")

    dry = store.backfill_goal_encryption(dry_run=True)
    applied = store.backfill_goal_encryption(dry_run=False)

    assert dry["scanned"] == applied["scanned"] == 2
    assert dry["changed"] == applied["changed"] == 2


def test_backfill_preserves_cross_tenant_isolation(store):
    _insert_legacy_row(store, session_id="s-a", goal="目标 A")
    _insert_legacy_row(
        store,
        session_id="s-b",
        goal="目标 B",
        tenant_id="tenant-other",
    )

    store.backfill_goal_encryption(dry_run=False)

    loaded_a = store.load("s-a", _TENANT)
    loaded_b = store.load("s-b", "tenant-other")
    assert loaded_a is not None
    assert loaded_a.goal == "目标 A"
    assert store.load("s-a", "tenant-other") is None
    assert loaded_b is not None
    assert loaded_b.goal == "目标 B"
    assert store.load("s-b", _TENANT) is None
