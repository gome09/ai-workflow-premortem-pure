"""Eval experiment claim coordination: lease-based single-runner ownership.

Revision ID: V014
Revises: V013
Create Date: 2026-11-14

Changes
-------
1. eval_experiments.claim_owner — opaque per-runner token; NULL when idle.
2. eval_experiments.claim_attempt — monotonic claim attempt, never decreases.
3. eval_experiments.claim_request_key — idempotency key of the accepted request.
4. eval_experiments.claim_heartbeat_at — last heartbeat (DB clock).
5. eval_experiments.claim_lease_until — lease deadline (DB clock).

The columns are coordinated by the storage layer only; projection sync
(``_sync_eval_experiments``) never overwrites them.
"""

from __future__ import annotations

from alembic import op

revision = "V014"
down_revision = "V013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE eval_experiments ADD COLUMN IF NOT EXISTS claim_owner TEXT")
    op.execute(
        "ALTER TABLE eval_experiments ADD COLUMN IF NOT EXISTS claim_attempt "
        "INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE eval_experiments ADD COLUMN IF NOT EXISTS claim_request_key "
        "TEXT NOT NULL DEFAULT ''"
    )
    op.execute(
        "ALTER TABLE eval_experiments ADD COLUMN IF NOT EXISTS claim_heartbeat_at TIMESTAMPTZ"
    )
    op.execute(
        "ALTER TABLE eval_experiments ADD COLUMN IF NOT EXISTS claim_lease_until TIMESTAMPTZ"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE eval_experiments DROP COLUMN IF EXISTS claim_lease_until")
    op.execute("ALTER TABLE eval_experiments DROP COLUMN IF EXISTS claim_heartbeat_at")
    op.execute("ALTER TABLE eval_experiments DROP COLUMN IF EXISTS claim_request_key")
    op.execute("ALTER TABLE eval_experiments DROP COLUMN IF EXISTS claim_attempt")
    op.execute("ALTER TABLE eval_experiments DROP COLUMN IF EXISTS claim_owner")
