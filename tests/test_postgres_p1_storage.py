"""PostgreSQL-only P1 storage verification (no Redis dependency).

Run with:
    E2E_DATABASE_URL=... STORAGE_BACKEND=postgres DATA_ENCRYPTION_KEY=... \
    PRODUCTION_SAFETY_REQUIRED=1 uv run pytest tests/test_postgres_p1_storage.py -q
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest

_REQUIRED = os.environ.get("PRODUCTION_SAFETY_REQUIRED") == "1"
_DATABASE_URL = os.environ.get("E2E_DATABASE_URL", "")
_ENCRYPTION_KEY = os.environ.get("DATA_ENCRYPTION_KEY", "")

if not _DATABASE_URL:
    message = "PostgreSQL P1 storage test requires E2E_DATABASE_URL."
    if _REQUIRED:
        pytest.fail(message, pytrace=False)
    pytest.skip(message, allow_module_level=True)

import json  # noqa: E402

import psycopg  # noqa: E402

from core.config import settings  # noqa: E402
from core.models import ProjectContext  # noqa: E402
from storage.field_security import _reset_fernet_cache  # noqa: E402
from storage.session_store import session_store  # noqa: E402


def _raw_context(session_id: str) -> str:
    with psycopg.connect(_DATABASE_URL) as conn:
        row = conn.execute(
            "SELECT context_json::text FROM sessions WHERE session_id = %s",
            (session_id,),
        ).fetchone()
    assert row is not None
    return str(row[0])


@pytest.fixture(scope="module", autouse=True)
def _runtime() -> None:
    if settings.storage_backend != "postgres":
        pytest.fail("This test requires STORAGE_BACKEND=postgres", pytrace=False)
    if not _ENCRYPTION_KEY:
        pytest.fail("This test requires DATA_ENCRYPTION_KEY", pytrace=False)
    _reset_fernet_cache()
    session_store.initialize()


@pytest.fixture
def tenant_id() -> str:
    return str(session_store.create_tenant(f"p1-test-{uuid.uuid4().hex}")["tenant_id"])


def test_goal_is_ciphertext_at_rest_and_decrypts(tenant_id):
    ctx = ProjectContext(tenant_id=tenant_id)
    ctx.data_classification = "business_internal"
    ctx.goal = "PG secret goal"
    ctx.research_target = "PG target"
    session_store.save(ctx)

    raw = _raw_context(ctx.session_id)
    assert "enc:v1:" in raw
    assert "PG secret goal" not in raw
    assert "PG target" not in raw

    loaded = session_store.load(ctx.session_id, tenant_id)
    assert loaded is not None
    assert loaded.goal == "PG secret goal"
    assert loaded.research_target == "PG target"

    session_store.delete(ctx.session_id, tenant_id, system_access=None)


def test_legacy_plaintext_goal_backfill(tenant_id):
    session_id = str(uuid.uuid4())
    legacy_goal = "PG legacy plaintext goal"
    context = {
        "context_schema_version": "0.10.0",
        "session_id": session_id,
        "tenant_id": tenant_id,
        "goal": legacy_goal,
        "data_classification": "business_internal",
        "current_state": "init",
    }
    with psycopg.connect(_DATABASE_URL) as conn:
        conn.execute(
            "INSERT INTO sessions "
            "(session_id, current_state, context_json, tenant_id, created_at, updated_at) "
            "VALUES (%s, %s, %s::jsonb, %s::uuid, NOW(), NOW())",
            (session_id, "init", json.dumps(context, ensure_ascii=False), tenant_id),
        )
        conn.commit()

    result = session_store.backfill_goal_encryption(session_ids=[session_id], dry_run=False)
    assert result["changed"] == 1
    assert result["status_counts"] == {"encrypted": 1}
    raw = _raw_context(session_id)
    assert "enc:v1:" in raw
    assert legacy_goal not in raw

    loaded = session_store.load(session_id, tenant_id)
    assert loaded is not None
    assert loaded.goal == legacy_goal

    second = session_store.backfill_goal_encryption(session_ids=[session_id], dry_run=False)
    assert second["changed"] == 0
    session_store.delete(session_id, tenant_id, system_access=None)


def test_pg_workspace_invitation_and_refresh_role():
    from auth.jwt import verify_token
    from auth.service import auth_service

    suffix = uuid.uuid4().hex
    author = auth_service.register(
        f"p1-author-{suffix}@example.com", "author-pass", workspace_name="P1 Team"
    )
    assert author["role"] == "admin"

    invitation = auth_service.create_invitation(
        author["tenant_id"],
        f"p1-reviewer-{suffix}@example.com",
        "admin",
        author["user_id"],
    )
    reviewer = auth_service.accept_invitation(invitation["token"], "reviewer-pass")
    assert reviewer["tenant_id"] == author["tenant_id"]
    assert reviewer["role"] == "admin"

    auth_service.update_role(reviewer["user_id"], author["tenant_id"], "viewer")
    refreshed = auth_service.refresh(reviewer["refresh_token"])
    assert refreshed["role"] == "viewer"
    assert refreshed["tenant_id"] == author["tenant_id"]
    assert verify_token(refreshed["access_token"]).role == "viewer"


def test_pg_service_token_and_release_gate_audit(tenant_id):
    from auth.service_tokens import hash_service_token

    raw_token = f"pmgate_{uuid.uuid4().hex}"
    token_id = str(uuid.uuid4())
    created = session_store.create_service_token(
        token_id=token_id,
        tenant_id=tenant_id,
        name="ci",
        token_hash=hash_service_token(raw_token),
        scope="release_gate:read",
        created_by="admin-user",
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    assert created["tenant_id"] == tenant_id

    fetched = session_store.get_service_token_by_hash(hash_service_token(raw_token))
    assert fetched is not None
    assert fetched["token_id"] == token_id

    revoked = session_store.revoke_service_token(
        tenant_id=tenant_id,
        token_id=token_id,
        revoked_at=datetime.now(UTC),
    )
    assert revoked is not None
    assert revoked["revoked_at"] is not None

    check_id = str(uuid.uuid4())
    session_store.record_release_gate_check(
        check_id=check_id,
        tenant_id=tenant_id,
        token_id=token_id,
        session_id=str(uuid.uuid4()),
        decision="block",
        reason_code="approval_not_requested",
        approval_status="not_requested",
        approval_id="",
        evaluation_version_digest="d" * 64,
        evidence_digest="e" * 64,
        release_batch_id="",
    )
    with psycopg.connect(_DATABASE_URL) as conn:
        row = conn.execute(
            "SELECT decision, reason_code FROM release_gate_checks WHERE check_id = %s::uuid",
            (check_id,),
        ).fetchone()
    assert row is not None
    assert row[0] == "block"
    assert row[1] == "approval_not_requested"
