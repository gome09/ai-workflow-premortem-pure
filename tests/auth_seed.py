"""Test helpers for seeding authenticated members into SQLite test stores."""

from __future__ import annotations

from typing import Any


def seed_sqlite_user(
    store: Any,
    *,
    user_id: str,
    tenant_id: str,
    role: str = "admin",
    email: str | None = None,
) -> dict[str, str]:
    """Insert or replace one tenant/member row directly.

    Tests use deterministic user IDs in JWT ``sub`` claims; the production
    ``create_user`` path generates UUIDs, so the helper writes the fixture rows
    directly into the isolated SQLite store.
    """
    resolved_email = email or f"{user_id}@example.test"
    with store._get_conn() as conn:  # noqa: SLF001 - test fixture
        conn.execute(
            "INSERT OR IGNORE INTO tenants (tenant_id, name) VALUES (?, ?)",
            (tenant_id, f"Tenant {tenant_id}"),
        )
        conn.execute(
            "INSERT OR REPLACE INTO users (user_id, tenant_id, email, password_hash, role) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, tenant_id, resolved_email, "test-hash", role),
        )
        conn.commit()
    return {"user_id": user_id, "tenant_id": tenant_id, "role": role, "email": resolved_email}


def seed_sqlite_roles(
    store: Any,
    *,
    tenant_id: str,
    roles: tuple[str, ...] = ("viewer", "editor", "admin"),
) -> dict[str, dict[str, str]]:
    seeded: dict[str, dict[str, str]] = {}
    for role in roles:
        user_id = f"{role}-user-{tenant_id}"
        seeded[role] = seed_sqlite_user(store, user_id=user_id, tenant_id=tenant_id, role=role)
    return seeded
