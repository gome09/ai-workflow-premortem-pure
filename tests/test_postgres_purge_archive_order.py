"""T06: concurrent save/purge must not lose audit events (PostgreSQL only).

Run with:
    E2E_DATABASE_URL=... STORAGE_BACKEND=postgres DATA_ENCRYPTION_KEY=... \
    PRODUCTION_SAFETY_REQUIRED=1 uv run pytest tests/test_postgres_purge_archive_order.py -q
"""

from __future__ import annotations

import os
import threading
import uuid

import pytest

_REQUIRED = os.environ.get("PRODUCTION_SAFETY_REQUIRED") == "1"
_DATABASE_URL = os.environ.get("E2E_DATABASE_URL", "")
_ENCRYPTION_KEY = os.environ.get("DATA_ENCRYPTION_KEY", "")

if not _DATABASE_URL:
    message = "PostgreSQL purge/archive order test requires E2E_DATABASE_URL."
    if _REQUIRED:
        pytest.fail(message, pytrace=False)
    pytest.skip(message, allow_module_level=True)

import psycopg  # noqa: E402

from core.audit_service import append_audit_event  # noqa: E402
from core.config import settings  # noqa: E402
from core.models import ProjectContext  # noqa: E402
from storage.errors import StorageError  # noqa: E402
from storage.session_store import session_store  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _runtime() -> None:
    if settings.storage_backend != "postgres":
        pytest.fail("This test requires STORAGE_BACKEND=postgres", pytrace=False)
    if not _ENCRYPTION_KEY:
        pytest.fail("This test requires DATA_ENCRYPTION_KEY", pytrace=False)
    session_store.initialize()


@pytest.fixture
def tenant_id() -> str:
    return str(session_store.create_tenant(f"purge-order-{uuid.uuid4().hex}")["tenant_id"])


def _archived_ids(session_id: str) -> set[str]:
    with psycopg.connect(_DATABASE_URL) as conn:
        rows = conn.execute(
            "SELECT event_id FROM audit_events_archive WHERE original_session_id = %s",
            (session_id,),
        ).fetchall()
    return {str(row[0]) for row in rows}


def _active_audit_count(session_id: str) -> int:
    with psycopg.connect(_DATABASE_URL) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM audit_events WHERE session_id = %s", (session_id,)
        ).fetchone()
    return int(row[0]) if row else 0


def _new_session(tenant_id: str) -> ProjectContext:
    ctx = ProjectContext(tenant_id=tenant_id, session_name="purge-order")
    append_audit_event(
        ctx,
        actor="user",
        event_type="note",
        target_type="session",
        target_id=ctx.session_id,
        after={"note": "seed"},
    )
    session_store.create(ctx)
    return ctx


def test_save_committed_before_purge_is_archived(tenant_id):
    ctx = _new_session(tenant_id)
    loaded = session_store.load(ctx.session_id, tenant_id)
    assert loaded is not None
    append_audit_event(
        loaded,
        actor="user",
        event_type="note",
        target_type="session",
        target_id=loaded.session_id,
        after={"note": "before-purge"},
    )
    session_store.save(loaded)
    expected = _archived_ids(ctx.session_id) | {event.event_id for event in loaded.audit_events}

    outcome = session_store.purge_session(ctx.session_id, tenant_id, "admin", {})

    assert outcome.deleted is True
    archived = _archived_ids(ctx.session_id)
    assert expected.issubset(archived)
    assert _active_audit_count(ctx.session_id) == 0


def test_concurrent_save_and_purge_never_loses_committed_audit(tenant_id):
    for index in range(10):
        ctx = _new_session(tenant_id)
        barrier = threading.Barrier(2)
        committed: list[str] = []
        errors: list[BaseException] = []

        def writer() -> None:
            try:
                fresh = session_store.load(ctx.session_id, tenant_id)
                if fresh is None:
                    return
                event = append_audit_event(
                    fresh,
                    actor="user",
                    event_type="note",
                    target_type="session",
                    target_id=fresh.session_id,
                    after={"note": f"concurrent-{index}"},
                )
                barrier.wait(timeout=10)
                session_store.save(fresh)
                committed.append(event.event_id)
            except StorageError:
                # 删除先取锁时保存必须失败；失败前未提交的审计不应假装存在。
                pass
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        def purger() -> None:
            try:
                barrier.wait(timeout=10)
                session_store.purge_session(ctx.session_id, tenant_id, "admin", {})
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=writer), threading.Thread(target=purger)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        assert not errors
        assert all(not thread.is_alive() for thread in threads)
        if committed:
            archived = _archived_ids(ctx.session_id)
            assert set(committed).issubset(archived)


def test_archive_failure_rolls_back_purge(tenant_id, monkeypatch):
    ctx = _new_session(tenant_id)

    def explode(summary):
        raise RuntimeError("archive failure")

    monkeypatch.setattr("storage.backends.postgres.sanitize_purge_summary", explode)

    with pytest.raises(RuntimeError, match="archive failure"):
        session_store.purge_session(ctx.session_id, tenant_id, "admin", {})

    assert session_store.load(ctx.session_id, tenant_id) is not None
    assert _active_audit_count(ctx.session_id) >= 1
    assert _archived_ids(ctx.session_id) == set()
