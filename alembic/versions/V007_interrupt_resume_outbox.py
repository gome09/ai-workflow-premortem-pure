"""Durable outbox for LangGraph interrupt resume delivery.

Revision ID: V007
Revises: V006
Create Date: 2026-09-21
"""

from __future__ import annotations

from alembic import op

revision = "V007"
down_revision = "V006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS interrupt_resume_outbox (
        interrupt_id  TEXT PRIMARY KEY,
        session_id    TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        tenant_id     UUID,
        action_id     TEXT NOT NULL UNIQUE,
        thread_id     TEXT NOT NULL,
        checkpoint_ns TEXT NOT NULL DEFAULT '',
        resume_payload JSONB NOT NULL,
        status        TEXT NOT NULL DEFAULT 'pending',
        attempts      INTEGER NOT NULL DEFAULT 0,
        claimed_at    TIMESTAMPTZ,
        completed_at  TIMESTAMPTZ,
        last_error    TEXT,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT interrupt_resume_outbox_status_check
            CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
        CONSTRAINT interrupt_resume_outbox_attempts_check CHECK (attempts >= 0)
    )
    """)
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_interrupt_resume_outbox_pending
    ON interrupt_resume_outbox (status, updated_at, created_at)
    WHERE status IN ('pending', 'failed')
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_interrupt_resume_outbox_pending")
    op.execute("DROP TABLE IF EXISTS interrupt_resume_outbox")
