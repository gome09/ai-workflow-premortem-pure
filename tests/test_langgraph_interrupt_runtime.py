from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from core.execution_mode import WorkflowExecutionMode
from core.models import PendingHumanAction, ProjectContext
from graph import checkpoint_manager as checkpoint_runtime
from graph import langgraph_interrupt_runner as runner
from graph.interrupts import mark_interrupt_resumed_from_action, sync_interrupt_records


class _PolicyEffect:
    def __init__(self, *, allow_continue: bool) -> None:
        self.allow_continue = allow_continue
        self.require_revision = not allow_continue
        self.require_escalation = False
        self.message = "continue" if allow_continue else "stop"


class _RecordingGraph:
    def __init__(self, result: ProjectContext) -> None:
        self.result = result
        self.invocations: list[tuple[Any, dict[str, Any]]] = []

    def invoke(self, value: Any, *, config: dict[str, Any]) -> ProjectContext:
        self.invocations.append((value, config))
        return self.result


def _blocking_action(*, decision: str | None = None) -> PendingHumanAction:
    action = PendingHumanAction(
        action_id="action-1",
        session_id="session-1",
        stage_id=1,
        source_type="failure_mode",
        source_id="FM-1",
        action_type="approve",
        risk_level="high",
        title="Review high-risk output",
        description="A human decision is required.",
        blocking=True,
    )
    if decision is not None:
        action.status = "resolved"
        action.reviewer_decision = decision
    return action


def _reset_runner_runtime() -> None:
    runner._GRAPH_CACHE = None
    checkpoint_runtime.reset_interrupt_runtime_for_tests()


def test_real_langgraph_graph_pauses_at_blocking_review_gate(monkeypatch):
    """The opt-in adapter must create a genuine LangGraph interrupt/checkpoint."""
    from langgraph.checkpoint.memory import MemorySaver

    ctx = ProjectContext(session_id="session-1")

    def create_blocking_action(input_ctx: ProjectContext) -> ProjectContext:
        input_ctx.pending_actions.append(_blocking_action())
        return input_ctx

    saver = MemorySaver()
    monkeypatch.setattr(runner, "run_one_step", create_blocking_action)
    _reset_runner_runtime()
    monkeypatch.setattr(checkpoint_runtime.checkpoint_manager, "get_saver", lambda: saver)

    result = runner.invoke_one_turn_with_interrupts(ctx)

    assert result.pending_actions[0].action_id == "action-1"
    assert result.interrupt_records[0].status == "pending"
    checkpoints = list(saver.list(None))
    assert checkpoints
    checkpoint = checkpoints[0]
    assert checkpoint.config["configurable"][
        "thread_id"
    ] == checkpoint_runtime.checkpoint_thread_id(result)
    assert checkpoint.pending_writes
    interrupt_writes = [
        value
        for _task_id, channel, value in checkpoint.pending_writes
        if channel == "__interrupt__"
    ]
    assert interrupt_writes
    assert interrupt_writes[0][0].value["action_id"] == "action-1"


def test_resume_after_graph_rebuild_preserves_latest_business_state(monkeypatch):
    """A durable checkpoint must not overwrite the authoritative review decision."""
    from langgraph.checkpoint.memory import MemorySaver

    ctx = ProjectContext(session_id="session-1")
    action = _blocking_action()
    ctx.pending_actions.append(action)
    sync_interrupt_records(ctx)

    saver = MemorySaver()
    _reset_runner_runtime()
    monkeypatch.setattr(checkpoint_runtime.checkpoint_manager, "get_saver", lambda: saver)
    runner.invoke_one_turn_with_interrupts(ctx)

    # This copy represents ProjectContext reloaded from the business store after
    # a process restart and human approval. The graph cache is deliberately
    # rebuilt while the saver survives, as a PostgreSQL saver would.
    latest = ctx.model_copy(deep=True)
    latest_action = latest.pending_actions[0]
    latest_action.status = "resolved"
    latest_action.reviewer_decision = "approve"
    latest_action.reviewer_note = "Approved by reviewer"
    mark_interrupt_resumed_from_action(
        latest,
        latest_action.action_id,
        policy_effect=_PolicyEffect(allow_continue=True),
    )
    assert latest.interrupt_records[0].status == "resumed"
    runner._GRAPH_CACHE = None

    result = runner.consume_resumable_interrupt_if_needed(latest, latest_action.action_id)

    assert result.pending_actions[0].status == "resolved"
    assert result.pending_actions[0].reviewer_decision == "approve"
    assert result.pending_actions[0].reviewer_note == "Approved by reviewer"
    assert result.interrupt_records[0].resume_consumed_at is not None


def test_approved_interrupt_resume_is_consumed_exactly_once(monkeypatch):
    """Repeated resolution delivery must never emit a second Command(resume=...)."""
    ctx = ProjectContext(session_id="session-1")
    action = _blocking_action(decision="approve")
    ctx.pending_actions.append(action)
    sync_interrupt_records(ctx)
    mark_interrupt_resumed_from_action(
        ctx, action.action_id, policy_effect=_PolicyEffect(allow_continue=True)
    )
    assert ctx.interrupt_records[0].status == "resumed"

    graph = _RecordingGraph(ctx)
    monkeypatch.setattr(runner, "get_one_turn_interrupt_graph", lambda: graph)

    first = runner.consume_resumable_interrupt_if_needed(ctx, action.action_id)
    second = runner.consume_resumable_interrupt_if_needed(first, action.action_id)

    assert second.interrupt_records[0].resume_consumed_at is not None
    assert len(graph.invocations) == 1
    command, config = graph.invocations[0]
    assert command.resume["action_id"] == action.action_id
    assert config["configurable"]["thread_id"] == checkpoint_runtime.checkpoint_thread_id(ctx)


def test_rejected_action_never_invokes_resume(monkeypatch):
    from core import execution_service

    ctx = ProjectContext(session_id="session-1")
    action = _blocking_action()
    ctx.pending_actions.append(action)
    sync_interrupt_records(ctx)
    action.status = "resolved"
    action.reviewer_decision = "reject"

    graph = _RecordingGraph(ctx)
    monkeypatch.setattr(runner, "get_one_turn_interrupt_graph", lambda: graph)
    monkeypatch.setattr(
        execution_service.settings,
        "workflow_execution_mode",
        WorkflowExecutionMode.LANGGRAPH_INTERRUPT,
    )

    result = execution_service.sync_execution_after_action_resolution(
        ctx,
        action.action_id,
        policy_effect=_PolicyEffect(allow_continue=False),
        reason="Reviewer rejected the action.",
    )

    assert result.interrupt_records[0].status == "cancelled"
    assert result.interrupt_records[0].resume_consumed_at is None
    assert graph.invocations == []


def test_checkpoint_thread_id_is_tenant_scoped():
    first = ProjectContext(session_id="shared-session", tenant_id="tenant-a")
    second = ProjectContext(session_id="shared-session", tenant_id="tenant-b")

    assert checkpoint_runtime.checkpoint_thread_id(
        first
    ) != checkpoint_runtime.checkpoint_thread_id(second)


def test_failed_resume_is_not_marked_consumed(monkeypatch):
    ctx = ProjectContext(session_id="session-1")
    action = _blocking_action(decision="approve")
    ctx.pending_actions.append(action)
    sync_interrupt_records(ctx)
    mark_interrupt_resumed_from_action(
        ctx, action.action_id, policy_effect=_PolicyEffect(allow_continue=True)
    )

    class MissingCheckpointGraph:
        def invoke(self, value: Any, *, config: dict[str, Any]) -> ProjectContext:
            raise RuntimeError("checkpoint not found")

    monkeypatch.setattr(runner, "get_one_turn_interrupt_graph", MissingCheckpointGraph)

    result = runner.consume_resumable_interrupt_if_needed(ctx, action.action_id)

    assert result.interrupt_records[0].resume_consumed_at is None
    assert any(event.event_type == "interrupt_resume_failed" for event in result.audit_events)


def test_stage_version_mismatch_refuses_resume(monkeypatch):
    ctx = ProjectContext(session_id="session-1")
    action = _blocking_action(decision="approve")
    action.stage_output_version = 1
    ctx.pending_actions.append(action)
    sync_interrupt_records(ctx)
    mark_interrupt_resumed_from_action(
        ctx, action.action_id, policy_effect=_PolicyEffect(allow_continue=True)
    )
    ctx.stage_output_versions["stage_1"] = 2

    graph = _RecordingGraph(ctx)
    monkeypatch.setattr(runner, "get_one_turn_interrupt_graph", lambda: graph)

    result = runner.consume_resumable_interrupt_if_needed(ctx, action.action_id)

    assert graph.invocations == []
    assert result.interrupt_records[0].resume_consumed_at is None
    rejected = [
        event for event in result.audit_events if event.event_type == "interrupt_resume_rejected"
    ]
    assert rejected
    assert "mismatched" in rejected[-1].metadata["reason"]


@pytest.mark.parametrize(
    ("field", "tampered_value"),
    [
        ("thread_id", "tenant:attacker:session:session-1"),
        ("node_name", "stage_4_review_gate"),
        ("checkpoint_ns", "attacker_namespace"),
    ],
)
def test_locator_tampering_is_not_repaired_and_resume_is_rejected(
    monkeypatch, field: str, tampered_value: str
):
    ctx = ProjectContext(session_id="session-1", tenant_id="tenant-a")
    action = _blocking_action(decision="approve")
    ctx.pending_actions.append(action)
    sync_interrupt_records(ctx)
    mark_interrupt_resumed_from_action(
        ctx, action.action_id, policy_effect=_PolicyEffect(allow_continue=True)
    )
    record = ctx.interrupt_records[0]
    setattr(record, field, tampered_value)

    sync_interrupt_records(ctx)

    assert getattr(record, field) == tampered_value
    graph = _RecordingGraph(ctx)
    monkeypatch.setattr(runner, "get_one_turn_interrupt_graph", lambda: graph)

    result = runner.consume_resumable_interrupt_if_needed(ctx, action.action_id)

    assert graph.invocations == []
    assert result.interrupt_records[0].resume_consumed_at is None
    assert any(event.event_type == "interrupt_resume_rejected" for event in result.audit_events)


@pytest.mark.parametrize("decision", ["approve", "edit", "escalate"])
def test_generic_sync_never_infers_resume_for_resolved_actions(decision: str):
    ctx = ProjectContext(session_id="session-1")
    action = _blocking_action()
    ctx.pending_actions.append(action)
    sync_interrupt_records(ctx)
    action.status = "resolved"
    action.reviewer_decision = decision

    sync_interrupt_records(ctx)

    record = ctx.interrupt_records[0]
    assert record.status == "pending"
    assert record.resume_value is None
    assert record.resolved_at is None


def test_reconcile_claims_and_consumes_resumed_unconsumed_outbox(monkeypatch):
    from core import execution_service
    from storage import session_store as session_store_module

    ctx = ProjectContext(session_id="session-1", tenant_id="tenant-a")
    action = _blocking_action(decision="approve")
    ctx.pending_actions.append(action)
    sync_interrupt_records(ctx)
    mark_interrupt_resumed_from_action(
        ctx, action.action_id, policy_effect=_PolicyEffect(allow_continue=True)
    )
    record = ctx.interrupt_records[0]

    class FakeStore:
        def __init__(self) -> None:
            self.claims: list[str] = []
            self.saved: list[ProjectContext] = []
            self.completions: list[tuple[str, str]] = []

        def list_pending_interrupt_resumes(self, limit: int = 100) -> list[dict[str, str]]:
            assert limit == 100
            return [
                {
                    "interrupt_id": record.interrupt_id,
                    "session_id": ctx.session_id,
                    "tenant_id": ctx.tenant_id,
                    "action_id": action.action_id,
                }
            ]

        def claim_interrupt_resume(self, interrupt_id: str) -> bool:
            self.claims.append(interrupt_id)
            return True

        def load(self, session_id: str, tenant_id: str = "") -> ProjectContext | None:
            assert (session_id, tenant_id) == (ctx.session_id, ctx.tenant_id)
            return ctx

        def save(self, value: ProjectContext) -> None:
            self.saved.append(value)

        def complete_interrupt_resume(self, interrupt_id: str, error: str = "") -> None:
            self.completions.append((interrupt_id, error))

    store = FakeStore()
    graph = _RecordingGraph(ctx)
    monkeypatch.setattr(session_store_module, "session_store", store)
    monkeypatch.setattr(
        execution_service.settings,
        "workflow_execution_mode",
        WorkflowExecutionMode.LANGGRAPH_INTERRUPT,
    )
    monkeypatch.setattr(runner, "get_one_turn_interrupt_graph", lambda: graph)

    result = execution_service.reconcile_pending_interrupt_resumes()

    assert store.claims == [record.interrupt_id]
    assert len(graph.invocations) == 1
    assert record.resume_consumed_at is not None
    assert store.saved == [ctx]
    assert store.completions == [(record.interrupt_id, "")]
    assert result == {"found": 1, "claimed": 1, "completed": 1, "failed": 0}


def test_startup_runs_interrupt_resume_reconciliation(monkeypatch):
    from api import main

    calls: list[int] = []
    monkeypatch.setattr(main.session_store, "initialize", lambda: None)
    monkeypatch.setattr(main, "initialize_interrupt_runtime", lambda: None)
    monkeypatch.setattr(main, "close_interrupt_runtime", lambda: None)
    monkeypatch.setattr(
        main,
        "reconcile_pending_interrupt_resumes",
        lambda: calls.append(1) or {"scanned": 0, "claimed": 0, "consumed": 0, "failed": 0},
    )

    with TestClient(main.app):
        pass

    assert calls == [1]


def test_interrupt_adapter_health_reports_actual_runtime_state(monkeypatch):
    manager = checkpoint_runtime.CheckpointManager()
    monkeypatch.setattr(
        checkpoint_runtime.settings,
        "workflow_execution_mode",
        WorkflowExecutionMode.LANGGRAPH_INTERRUPT,
    )
    monkeypatch.setattr(
        manager,
        "initialize",
        lambda: (_ for _ in ()).throw(RuntimeError("checkpoint database unavailable")),
    )

    health = manager.health()

    assert health["status"] != "healthy"
    assert health["persistent"] is False
    assert "checkpoint" in health["detail"].lower()


def test_health_does_not_claim_adapter_is_healthy_when_probe_fails(monkeypatch):
    from api import main

    monkeypatch.setattr(
        main.settings,
        "workflow_execution_mode",
        WorkflowExecutionMode.LANGGRAPH_INTERRUPT,
    )
    monkeypatch.setattr(
        main,
        "get_interrupt_adapter_health",
        lambda: {
            "status": "unhealthy",
            "backend": "unavailable",
            "persistent": False,
            "encrypted": False,
            "detail": "checkpoint database unavailable",
        },
    )
    client = TestClient(main.app, raise_server_exceptions=False)

    legacy = client.get("/health")
    ready = client.get("/health/ready")

    assert legacy.status_code == 200
    assert legacy.json()["interrupt_adapter_status"] == "unhealthy"
    assert ready.status_code == 503
    assert ready.json()["checks"]["interrupt_adapter"] == "unhealthy"


def test_interrupt_health_contract_is_persistence_explicit(monkeypatch):
    """Operators must be able to distinguish durable checkpoints from dev memory."""
    manager = checkpoint_runtime.CheckpointManager()
    monkeypatch.setattr(
        checkpoint_runtime.settings,
        "workflow_execution_mode",
        WorkflowExecutionMode.LANGGRAPH_INTERRUPT,
    )
    monkeypatch.setattr(checkpoint_runtime.settings, "checkpoint_backend", "memory")
    monkeypatch.setattr(checkpoint_runtime.settings, "storage_backend", "sqlite")

    health = manager.health()

    assert set(health) >= {"status", "backend", "persistent", "encrypted", "detail"}
    assert health["backend"] == "memory"
    assert health["persistent"] is False
    assert health["encrypted"] is False
    assert health["status"] == "healthy"


def test_postgres_checkpointer_connection_is_durable_and_schema_setup_is_external(
    monkeypatch,
):
    """Alembic owns schema setup; the saver connection must meet its driver contract."""
    import psycopg
    from langgraph.checkpoint import postgres as checkpoint_postgres
    from psycopg.rows import dict_row

    connect_calls: list[tuple[str, dict[str, Any]]] = []

    class FakeResult:
        def fetchone(self) -> dict[str, int]:
            return {"v": 9}

    class FakeConnection:
        def execute(self, statement: str) -> FakeResult:
            if "checkpoint_migrations" in statement:
                return FakeResult()
            assert any(
                table in statement
                for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes")
            )
            return FakeResult()

    class FakeSaver:
        def __init__(self, connection: FakeConnection, *, serde: Any) -> None:
            self.connection = connection
            self.serde = serde

        def setup(self) -> None:
            raise AssertionError("runtime must not create checkpoint tables")

    fake_connection = FakeConnection()

    def fake_connect(dsn: str, **kwargs: Any) -> FakeConnection:
        connect_calls.append((dsn, kwargs))
        return fake_connection

    monkeypatch.setattr(psycopg, "connect", fake_connect)
    monkeypatch.setattr(checkpoint_postgres, "PostgresSaver", FakeSaver)
    monkeypatch.setattr(
        checkpoint_runtime.settings,
        "workflow_execution_mode",
        WorkflowExecutionMode.LANGGRAPH_INTERRUPT,
    )
    monkeypatch.setattr(checkpoint_runtime.settings, "checkpoint_backend", "postgres")
    monkeypatch.setattr(checkpoint_runtime.settings, "storage_backend", "postgres")
    monkeypatch.setattr(checkpoint_runtime.settings, "uvicorn_workers", 1)
    monkeypatch.setattr(
        checkpoint_runtime.settings,
        "checkpoint_encryption_key",
        "q-KZ_nwo7m_sNCzfP9x9M57VNk7Qb1CQ7qE9fL6p8FA=",
    )

    manager = checkpoint_runtime.CheckpointManager()
    manager.initialize()
    saver = manager.get_saver()

    assert isinstance(saver, FakeSaver)
    assert len(connect_calls) == 1
    _, kwargs = connect_calls[0]
    assert kwargs == {
        "autocommit": True,
        "prepare_threshold": 0,
        "row_factory": dict_row,
    }


def test_checkpoint_serializer_encrypts_sensitive_payload_and_round_trips():
    from cryptography.fernet import Fernet
    from langgraph.checkpoint.serde.encrypted import EncryptedSerializer

    marker = "sensitive-personal-marker-身份证-110101199001011234"
    payload = {
        "context": {
            "tenant_id": "tenant-secret",
            "user_materials": [marker],
        }
    }
    serializer = EncryptedSerializer(
        checkpoint_runtime._FernetCipher(Fernet.generate_key().decode("ascii"))
    )

    type_name, ciphertext = serializer.dumps_typed(payload)

    assert type_name.endswith("+fernet")
    assert marker.encode("utf-8") not in ciphertext
    assert b"tenant-secret" not in ciphertext
    assert serializer.loads_typed((type_name, ciphertext)) == payload


def test_postgres_checkpoint_cleanup_without_live_saver_is_tenant_scoped(monkeypatch):
    import psycopg

    statements: list[tuple[str, tuple[str]]] = []

    class FakeConnection:
        committed = False

        def __enter__(self) -> FakeConnection:
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def execute(self, statement: str, params: tuple[str]) -> None:
            statements.append((statement, params))

        def commit(self) -> None:
            self.committed = True

    connection = FakeConnection()
    monkeypatch.setattr(psycopg, "connect", lambda dsn: connection)
    monkeypatch.setattr(checkpoint_runtime.settings, "storage_backend", "postgres")
    monkeypatch.setattr(
        checkpoint_runtime.settings,
        "workflow_execution_mode",
        WorkflowExecutionMode.SINGLE_STEP,
    )
    manager = checkpoint_runtime.CheckpointManager()
    ctx = ProjectContext(session_id="same-session", tenant_id="tenant-a")

    manager.delete_thread(checkpoint_runtime.checkpoint_thread_id(ctx))

    expected_thread = "tenant:tenant-a:session:same-session"
    assert [sql.split()[2] for sql, _params in statements] == [
        "checkpoint_writes",
        "checkpoint_blobs",
        "checkpoints",
    ]
    assert all(params == (expected_thread,) for _sql, params in statements)
    assert connection.committed is True


def test_interrupt_resume_claim_is_atomic_under_competing_workers(monkeypatch):
    from storage.backends.postgres import PostgresSessionStore

    class ClaimResult:
        def __init__(self, rowcount: int) -> None:
            self.rowcount = rowcount

    class SharedClaimConnection:
        claimed = False

        def __enter__(self) -> SharedClaimConnection:
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def execute(self, sql: str, params: tuple[str]) -> ClaimResult:
            assert "UPDATE interrupt_resume_outbox" in sql
            assert "WHERE interrupt_id = %s" in sql
            assert "pending" in sql
            if self.claimed:
                return ClaimResult(0)
            self.claimed = True
            return ClaimResult(1)

        def commit(self) -> None:
            return None

    connection = SharedClaimConnection()
    store = PostgresSessionStore()
    monkeypatch.setattr(store, "_get_conn", lambda: connection)

    first = store.claim_interrupt_resume("INT-1")
    second = store.claim_interrupt_resume("INT-1")

    assert first is True
    assert second is False


def test_business_purge_failure_rolls_back_without_session_purged(monkeypatch):
    from storage.backends.postgres import PostgresSessionStore

    class FakeRows:
        def fetchall(self) -> list[dict[str, Any]]:
            return []

    class FailingPurgeConnection:
        def __init__(self) -> None:
            self.statements: list[str] = []
            self.committed = False
            self.rolled_back = False

        def __enter__(self) -> FailingPurgeConnection:
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            if exc_type is not None:
                self.rolled_back = True
            return None

        def execute(self, sql: str, params: tuple[Any, ...]) -> Any:
            self.statements.append(sql)
            if sql.lstrip().startswith("SELECT event_id"):
                return FakeRows()
            if sql.lstrip().startswith("DELETE FROM sessions"):
                raise RuntimeError("business delete failed")
            return None

        def commit(self) -> None:
            self.committed = True

    connection = FailingPurgeConnection()
    store = PostgresSessionStore()
    monkeypatch.setattr(store, "_get_conn", lambda: connection)

    with pytest.raises(RuntimeError, match="business delete failed"):
        store.purge_session(
            "session-1",
            "tenant-a",
            "admin-user",
            {"session_id": "session-1", "tenant_id": "tenant-a"},
        )

    assert connection.committed is False
    assert connection.rolled_back is True
    # The INSERT may have run, but rollback guarantees no durable false purge audit.
    assert any(
        "session_purged" in sql or "audit_events_archive" in sql for sql in connection.statements
    )


def test_session_delete_keeps_session_when_checkpoint_cleanup_fails(monkeypatch):
    from core import session_service as session_service_module
    from core.session_service import SessionService

    ctx = ProjectContext(session_id="session-keep", tenant_id="tenant-a")

    class FakeStore:
        def __init__(self) -> None:
            self.context = ctx
            self.archive_calls: list[Any] = []
            self.delete_calls: list[Any] = []

        def load(self, session_id: str, tenant_id: str) -> ProjectContext | None:
            if session_id == ctx.session_id and tenant_id == ctx.tenant_id:
                return self.context
            return None

        def archive_audit_events(self, *args: Any) -> int:
            self.archive_calls.append(args)
            return 1

        def delete(self, *args: Any) -> None:
            self.delete_calls.append(args)
            self.context = None

    class FakeCache:
        def __init__(self) -> None:
            self.delete_calls: list[Any] = []

        def get(self, session_id: str, tenant_id: str) -> None:
            return None

        def set(self, value: ProjectContext) -> None:
            return None

        def delete(self, *args: Any) -> None:
            self.delete_calls.append(args)

    store = FakeStore()
    cache = FakeCache()
    monkeypatch.setattr(session_service_module, "session_store", store)
    monkeypatch.setattr(session_service_module, "context_cache", cache)
    monkeypatch.setattr(
        checkpoint_runtime,
        "delete_session_checkpoints",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("cleanup failed")),
    )

    service = SessionService()
    try:
        service.delete_session(ctx.session_id, tenant_id=ctx.tenant_id)
    except RuntimeError as exc:
        assert str(exc) == "cleanup failed"
    else:
        raise AssertionError("checkpoint cleanup failure must abort session deletion")

    assert store.load(ctx.session_id, ctx.tenant_id) is ctx
    assert store.archive_calls == []
    assert store.delete_calls == []
    assert cache.delete_calls == []
