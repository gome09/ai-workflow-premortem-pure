"""Lifecycle and health management for the LangGraph checkpointer.

PostgreSQL is the durable production backend.  The in-memory backend is kept
only for explicitly configured local/SQLite development and tests.
"""

from __future__ import annotations

import logging
from threading import RLock
from typing import Any

from cryptography.fernet import Fernet

from core.config import settings
from core.execution_mode import WorkflowExecutionMode

logger = logging.getLogger(__name__)

_CHECKPOINT_NAMESPACE = "ai_workflow_v1_review_gate"
_EXPECTED_CHECKPOINT_MIGRATION = 9


class InterruptRuntimeError(RuntimeError):
    """Raised when the selected interrupt runtime cannot operate safely."""


class _FernetCipher:
    """Adapter from cryptography.Fernet to LangGraph's CipherProtocol."""

    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode("ascii"))

    def encrypt(self, plaintext: bytes) -> tuple[str, bytes]:
        return "fernet", self._fernet.encrypt(plaintext)

    def decrypt(self, ciphername: str, ciphertext: bytes) -> bytes:
        if ciphername != "fernet":
            raise ValueError(f"Unsupported checkpoint cipher: {ciphername}")
        return self._fernet.decrypt(ciphertext)


def checkpoint_thread_id(ctx: Any) -> str:
    """Return a tenant-scoped stable thread identifier."""
    tenant_id = str(getattr(ctx, "tenant_id", "") or "default")
    session_id = str(getattr(ctx, "session_id", ""))
    return f"tenant:{tenant_id}:session:{session_id}"


class CheckpointManager:
    def __init__(self) -> None:
        self._lock = RLock()
        self._saver: Any | None = None
        self._resource: Any | None = None
        self._backend = "disabled"
        self._persistent = False
        self._encrypted = False
        self._detail = "single_step execution mode"

    def initialize(self) -> None:
        mode = WorkflowExecutionMode.normalize(settings.workflow_execution_mode)
        if mode != WorkflowExecutionMode.LANGGRAPH_INTERRUPT:
            return

        with self._lock:
            if self._saver is not None:
                return

            backend = str(settings.checkpoint_backend).strip().lower()
            if backend == "memory":
                if settings.storage_backend != "sqlite":
                    raise InterruptRuntimeError(
                        "CHECKPOINT_BACKEND=memory is allowed only with STORAGE_BACKEND=sqlite"
                    )
                from langgraph.checkpoint.memory import MemorySaver

                self._saver = MemorySaver()
                self._resource = self._saver
                self._backend = "memory"
                self._persistent = False
                self._encrypted = False
                self._detail = "non-persistent local development backend"
                return

            if backend != "postgres":
                raise InterruptRuntimeError(
                    f"Unsupported CHECKPOINT_BACKEND={backend!r}; allowed: postgres, memory"
                )
            if settings.storage_backend == "sqlite":
                raise InterruptRuntimeError(
                    "CHECKPOINT_BACKEND=postgres requires STORAGE_BACKEND=postgres"
                )
            if settings.uvicorn_workers != 1:
                raise InterruptRuntimeError(
                    "langgraph_interrupt currently requires UVICORN_WORKERS=1"
                )
            if not settings.checkpoint_encryption_key:
                raise InterruptRuntimeError(
                    "CHECKPOINT_ENCRYPTION_KEY is required for PostgreSQL checkpoints"
                )

            try:
                import psycopg
                from langgraph.checkpoint.postgres import PostgresSaver
                from langgraph.checkpoint.serde.encrypted import EncryptedSerializer
                from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
                from psycopg.rows import dict_row

                serde = EncryptedSerializer(
                    _FernetCipher(settings.checkpoint_encryption_key),
                    serde=JsonPlusSerializer(
                        allowed_msgpack_modules=[
                            ("core.models", "ProjectContext"),
                            ("core.models", "SessionState"),
                        ]
                    ),
                )
                conn = psycopg.connect(
                    settings.postgres_dsn_sync,
                    autocommit=True,
                    prepare_threshold=0,
                    row_factory=dict_row,
                )
                self._validate_postgres_schema(conn)
                self._saver = PostgresSaver(conn, serde=serde)
                self._resource = conn
                self._backend = "postgres"
                self._persistent = True
                self._encrypted = True
                self._detail = "PostgreSQL checkpoint backend ready"
            except Exception as exc:
                self.close()
                raise InterruptRuntimeError(
                    f"PostgreSQL checkpoint initialization failed: {exc}"
                ) from exc

    @staticmethod
    def _validate_postgres_schema(conn: Any) -> None:
        row = conn.execute("SELECT v FROM checkpoint_migrations ORDER BY v DESC LIMIT 1").fetchone()
        version = row["v"] if isinstance(row, dict) else (row[0] if row else None)
        if version != _EXPECTED_CHECKPOINT_MIGRATION:
            raise InterruptRuntimeError(
                "LangGraph checkpoint schema is not at the expected migration "
                f"version {_EXPECTED_CHECKPOINT_MIGRATION} (found {version!r})"
            )
        for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()  # noqa: S608

    def get_saver(self) -> Any:
        self.initialize()
        if self._saver is None:
            raise InterruptRuntimeError("LangGraph interrupt runtime is not enabled")
        return self._saver

    def health(self) -> dict[str, Any]:
        mode = WorkflowExecutionMode.normalize(settings.workflow_execution_mode)
        if mode != WorkflowExecutionMode.LANGGRAPH_INTERRUPT:
            return {
                "status": "disabled",
                "backend": "disabled",
                "persistent": False,
                "encrypted": False,
                "detail": "single_step execution mode",
            }
        try:
            self.initialize()
            if self._backend == "postgres":
                resource = self._resource
                if resource is None:
                    raise InterruptRuntimeError("PostgreSQL checkpoint connection is unavailable")
                self._validate_postgres_schema(resource)
            return {
                "status": "healthy",
                "backend": self._backend,
                "persistent": self._persistent,
                "encrypted": self._encrypted,
                "detail": self._detail,
            }
        except Exception as exc:
            return {
                "status": "unhealthy",
                "backend": str(getattr(settings, "checkpoint_backend", "unknown")),
                "persistent": False,
                "encrypted": False,
                "detail": str(exc),
            }

    def delete_thread(self, thread_id: str) -> None:
        """Delete checkpoint state for a purged session when supported."""
        if self._saver is not None:
            delete_thread = getattr(self._saver, "delete_thread", None)
            if callable(delete_thread):
                delete_thread(thread_id)
                return
        if settings.storage_backend == "sqlite":
            return

        # Lifecycle cleanup is independent of the currently selected workflow
        # mode. A session created under interrupt mode may be purged after an
        # operator has rolled the service back to single_step.
        import psycopg

        with psycopg.connect(settings.postgres_dsn_sync) as conn:
            for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                conn.execute(f"DELETE FROM {table} WHERE thread_id = %s", (thread_id,))  # noqa: S608
            conn.commit()

    def close(self) -> None:
        with self._lock:
            resource = self._resource
            self._saver = None
            self._resource = None
            self._backend = "disabled"
            self._persistent = False
            self._encrypted = False
            self._detail = "not initialized"
            close = getattr(resource, "close", None)
            if callable(close):
                close()


checkpoint_manager = CheckpointManager()


def initialize_interrupt_runtime() -> None:
    checkpoint_manager.initialize()


def close_interrupt_runtime() -> None:
    checkpoint_manager.close()


def reset_interrupt_runtime_for_tests() -> None:
    checkpoint_manager.close()


def get_interrupt_adapter_health() -> dict[str, Any]:
    return checkpoint_manager.health()


def delete_session_checkpoints(ctx: Any, *, persistent: bool | None = None) -> None:
    if persistent is False and checkpoint_manager._saver is None:
        return
    checkpoint_manager.delete_thread(checkpoint_thread_id(ctx))


def checkpoint_namespace() -> str:
    return _CHECKPOINT_NAMESPACE
