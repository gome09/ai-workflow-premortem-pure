"""Release gate: tenant-scoped service tokens and check audit rows.

Revision ID: V013
Revises: V012
Create Date: 2026-11-07

Changes
-------
1. service_tokens — revocable tenant-scoped machine credentials for the
   read-only release gate endpoint. Only a SHA-256 hash is stored.
2. release_gate_checks — append-only audit of every authenticated gate check.

Both are new tables; no existing table is altered.
"""

from __future__ import annotations

from alembic import op

revision = "V013"
down_revision = "V012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS service_tokens (
            token_id     UUID PRIMARY KEY,
            tenant_id    UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
            name         TEXT NOT NULL,
            token_hash   TEXT NOT NULL,
            scope        TEXT NOT NULL DEFAULT 'release_gate:read',
            created_by   TEXT,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at   TIMESTAMPTZ NOT NULL,
            revoked_at   TIMESTAMPTZ,
            last_used_at TIMESTAMPTZ,
            CONSTRAINT service_tokens_scope_check
                CHECK (scope IN ('release_gate:read'))
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_service_tokens_token_hash "
        "ON service_tokens (token_hash)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_service_tokens_tenant "
        "ON service_tokens (tenant_id, created_at DESC)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS release_gate_checks (
            check_id                  UUID PRIMARY KEY,
            tenant_id                 UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
            token_id                  UUID REFERENCES service_tokens(token_id) ON DELETE SET NULL,
            session_id                TEXT NOT NULL,
            decision                  TEXT NOT NULL,
            reason_code               TEXT NOT NULL,
            approval_status           TEXT NOT NULL,
            approval_id               TEXT NOT NULL DEFAULT '',
            evaluation_version_digest TEXT NOT NULL DEFAULT '',
            evidence_digest           TEXT NOT NULL DEFAULT '',
            release_batch_id          TEXT NOT NULL DEFAULT '',
            checked_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT release_gate_checks_decision_check
                CHECK (decision IN ('allow', 'block'))
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_release_gate_checks_tenant_time "
        "ON release_gate_checks (tenant_id, checked_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_release_gate_checks_session "
        "ON release_gate_checks (session_id, checked_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS release_gate_checks")
    op.execute("DROP TABLE IF EXISTS service_tokens")
