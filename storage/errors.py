"""Storage-layer error taxonomy shared by backends and API adapters."""

from __future__ import annotations


class StorageError(RuntimeError):
    """Base class for storage failures that map to explicit API responses."""


class TenantIsolationError(StorageError):
    """Raised when a tenant-scoped operation is attempted without a valid tenant."""

    def __init__(self, session_id: str, operation: str = "access") -> None:
        self.session_id = session_id
        self.operation = operation
        super().__init__(f"Tenant isolation violation during {operation}: session={session_id}")


class StaleContextError(StorageError):
    """Raised when a save is based on an outdated stored version (lost-update guard)."""

    def __init__(self, session_id: str, expected_version: int, actual_version: int) -> None:
        self.session_id = session_id
        self.expected_version = expected_version
        self.actual_version = actual_version
        super().__init__(
            "Stale context: session="
            f"{session_id}, expected_version={expected_version}, actual_version={actual_version}"
        )
