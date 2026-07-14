# tests/test_field_encryption.py
"""T1.3 字段级静态加密 (field-level encryption) tests.

Covers:
- No key configured → encryption disabled, data unchanged.
- With key → user_materials / evidence_sources summary+claims encrypted (enc:v1: prefix).
- Round-trip: encrypt then decrypt restores original.
- public_demo never encrypted even with key configured.
- Idempotent: encrypting an already-encrypted value does not double-encrypt.
- SQLite backend round-trip with key: raw context_json contains enc:v1:, load() restores plaintext.
- SQLite backend no-key round-trip: plaintext stored and restored.
"""

from __future__ import annotations

import json

import pytest
from cryptography.fernet import Fernet

from core.config import settings
from core.models import EvidenceSource, ProjectContext
from storage.backends.sqlite_store import SQLiteSessionStore
from storage.field_security import (
    _encrypt_value,
    _reset_fernet_cache,
    decrypt_fields_after_load,
    encrypt_fields_for_storage,
    is_encryption_enabled,
)

_TEST_KEY = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def _reset_encryption_cache():
    """Reset Fernet cache before and after each test so settings changes take effect."""
    _reset_fernet_cache()
    yield
    _reset_fernet_cache()


# ── 1: No key = no encryption ─────────────────────────────────────────
def test_no_key_means_encryption_disabled(monkeypatch):
    monkeypatch.setattr(settings, "data_encryption_key", "")
    assert is_encryption_enabled() is False

    data = {
        "user_materials": ["secret text"],
        "evidence_sources": [
            {"source_type": "user_material", "summary": "s", "claims": ["c1", "c2"]}
        ],
    }
    result = encrypt_fields_for_storage(data, "business_internal")
    assert result["user_materials"] == ["secret text"]
    assert result["evidence_sources"][0]["summary"] == "s"
    assert result["evidence_sources"][0]["claims"] == ["c1", "c2"]


# ── 2: With key = encryption works ────────────────────────────────────
def test_with_key_encrypts_user_materials(monkeypatch):
    monkeypatch.setattr(settings, "data_encryption_key", _TEST_KEY)
    assert is_encryption_enabled() is True

    data = {
        "user_materials": ["secret text", "another secret"],
        "evidence_sources": [
            {
                "source_type": "user_material",
                "summary": "confidential summary",
                "claims": ["claim one", "claim two"],
            },
            {
                "source_type": "paper",  # non-user_material — must NOT be encrypted
                "summary": "public paper summary",
                "claims": ["public claim"],
            },
        ],
    }
    result = encrypt_fields_for_storage(data, "business_internal")

    # user_materials encrypted
    for m in result["user_materials"]:
        assert m.startswith("enc:v1:")

    # evidence_sources[0] (user_material) summary + claims encrypted
    ev0 = result["evidence_sources"][0]
    assert ev0["summary"].startswith("enc:v1:")
    for c in ev0["claims"]:
        assert c.startswith("enc:v1:")

    # evidence_sources[1] (paper) untouched
    ev1 = result["evidence_sources"][1]
    assert ev1["summary"] == "public paper summary"
    assert ev1["claims"] == ["public claim"]


# ── 3: Decrypt round-trip ─────────────────────────────────────────────
def test_decrypt_round_trip(monkeypatch):
    monkeypatch.setattr(settings, "data_encryption_key", _TEST_KEY)

    data = {
        "user_materials": ["secret text"],
        "evidence_sources": [
            {
                "source_type": "user_material",
                "summary": "confidential summary",
                "claims": ["claim one", "claim two"],
            }
        ],
    }
    encrypt_fields_for_storage(data, "business_internal")

    ctx = ProjectContext()
    ctx.user_materials = data["user_materials"]
    ctx.evidence_sources = [
        EvidenceSource(
            session_id=ctx.session_id,
            title="t",
            source_type="user_material",
            summary=data["evidence_sources"][0]["summary"],
            claims=data["evidence_sources"][0]["claims"],
        )
    ]
    decrypt_fields_after_load(ctx)

    assert ctx.user_materials == ["secret text"]
    assert ctx.evidence_sources[0].summary == "confidential summary"
    assert ctx.evidence_sources[0].claims == ["claim one", "claim two"]


# ── 4: public_demo not encrypted ──────────────────────────────────────
def test_public_demo_not_encrypted(monkeypatch):
    monkeypatch.setattr(settings, "data_encryption_key", _TEST_KEY)
    assert is_encryption_enabled() is True

    data = {
        "user_materials": ["should stay plaintext"],
        "evidence_sources": [
            {
                "source_type": "user_material",
                "summary": "plain summary",
                "claims": ["plain claim"],
            }
        ],
    }
    result = encrypt_fields_for_storage(data, "public_demo")
    assert result["user_materials"] == ["should stay plaintext"]
    assert result["evidence_sources"][0]["summary"] == "plain summary"
    assert result["evidence_sources"][0]["claims"] == ["plain claim"]


# ── 5: Idempotent encryption ──────────────────────────────────────────
def test_encryption_is_idempotent(monkeypatch):
    monkeypatch.setattr(settings, "data_encryption_key", _TEST_KEY)

    plain = "idempotent secret"
    encrypted_once = _encrypt_value(plain)
    assert encrypted_once.startswith("enc:v1:")

    encrypted_twice = _encrypt_value(encrypted_once)
    assert encrypted_twice == encrypted_once  # not double-encrypted


# ── 6: SQLite backend round-trip with key ─────────────────────────────
def test_sqlite_round_trip_with_key(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_encryption_key", _TEST_KEY)

    db_path = tmp_path / "workflow.db"
    store = SQLiteSessionStore(str(db_path))
    store.initialize()

    ctx = ProjectContext()
    ctx.data_classification = "business_internal"
    ctx.user_materials = ["secret text"]
    ctx.evidence_sources = [
        EvidenceSource(
            session_id=ctx.session_id,
            title="user-provided evidence",
            source_type="user_material",
            summary="confidential summary",
            claims=["claim one", "claim two"],
        )
    ]

    store.save(ctx)

    # Raw context_json in DB must contain the enc:v1: prefix
    with store._get_conn() as conn:  # noqa: SLF001  # direct DB introspection for test
        row = conn.execute(
            "SELECT context_json FROM sessions WHERE session_id=?",
            (ctx.session_id,),
        ).fetchone()
    raw_json = row["context_json"]
    assert "enc:v1:" in raw_json
    assert "secret text" not in raw_json
    assert "confidential summary" not in raw_json

    # load() must restore plaintext
    loaded = store.load(ctx.session_id)
    assert loaded is not None
    assert loaded.user_materials == ["secret text"]
    assert loaded.evidence_sources[0].summary == "confidential summary"
    assert loaded.evidence_sources[0].claims == ["claim one", "claim two"]


# ── 7: SQLite backend no-key round-trip ───────────────────────────────
def test_sqlite_round_trip_without_key(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_encryption_key", "")

    db_path = tmp_path / "workflow.db"
    store = SQLiteSessionStore(str(db_path))
    store.initialize()

    ctx = ProjectContext()
    ctx.data_classification = "business_internal"
    ctx.user_materials = ["plaintext secret"]
    ctx.evidence_sources = [
        EvidenceSource(
            session_id=ctx.session_id,
            title="user-provided evidence",
            source_type="user_material",
            summary="plaintext summary",
            claims=["plain claim"],
        )
    ]

    store.save(ctx)

    # Raw context_json stores plaintext (no enc: prefix)
    with store._get_conn() as conn:  # noqa: SLF001
        row = conn.execute(
            "SELECT context_json FROM sessions WHERE session_id=?",
            (ctx.session_id,),
        ).fetchone()
    raw_json = row["context_json"]
    assert "enc:v1:" not in raw_json
    assert "plaintext secret" in raw_json

    # load() restores plaintext unchanged
    loaded = store.load(ctx.session_id)
    assert loaded is not None
    assert loaded.user_materials == ["plaintext secret"]
    assert loaded.evidence_sources[0].summary == "plaintext summary"
    assert loaded.evidence_sources[0].claims == ["plain claim"]


# Sanity: ensure raw_json is parseable in case the assertion helper above misleads
def test_raw_context_json_is_valid_json(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_encryption_key", _TEST_KEY)

    db_path = tmp_path / "workflow.db"
    store = SQLiteSessionStore(str(db_path))
    store.initialize()

    ctx = ProjectContext()
    ctx.data_classification = "business_internal"
    ctx.user_materials = ["secret text"]
    store.save(ctx)

    with store._get_conn() as conn:  # noqa: SLF001
        row = conn.execute(
            "SELECT context_json FROM sessions WHERE session_id=?",
            (ctx.session_id,),
        ).fetchone()
    # Must still be valid JSON (encryption happens before json.dumps)
    parsed = json.loads(row["context_json"])
    assert isinstance(parsed, dict)
    assert parsed["user_materials"][0].startswith("enc:v1:")
