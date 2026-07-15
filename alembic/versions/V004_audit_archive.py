"""Audit events archive table for session purge audit trail.

Revision ID: V004
Revises: V003
Create Date: 2026-07-14

Changes
-------
1. audit_events_archive — CREATE TABLE (no FK to sessions; preserves audit trail after session deletion)
"""

from __future__ import annotations

from alembic import op

revision = "V004"
down_revision = "V003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS audit_events_archive (
        archive_id           TEXT PRIMARY KEY,
        original_session_id  TEXT NOT NULL,
        event_id             TEXT NOT NULL,
        actor                TEXT NOT NULL,
        event_type           TEXT NOT NULL,
        target_type          TEXT NOT NULL,
        target_id            TEXT NOT NULL,
        before_hash          TEXT,
        after_hash           TEXT,
        before_snapshot      JSONB,
        after_snapshot       JSONB,
        metadata             JSONB NOT NULL DEFAULT '{}',
        original_created_at  TIMESTAMPTZ NOT NULL,
        archived_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_archive_session "
        "ON audit_events_archive (original_session_id, original_created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_events_archive CASCADE")
