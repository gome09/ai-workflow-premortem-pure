"""gate_evaluation_records table for governance trend analytics.

Revision ID: V005
Revises: V004
Create Date: 2026-07-14

Changes
-------
1. gate_evaluation_records — CREATE TABLE (旁路写入，记录每次阶段门禁评估)
"""

from __future__ import annotations

from alembic import op

revision = "V005"
down_revision = "V004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS gate_evaluation_records (
        record_id            TEXT PRIMARY KEY,
        session_id           TEXT NOT NULL,
        tenant_id            TEXT,
        stage_id             INTEGER NOT NULL,
        risk_tier            TEXT NOT NULL,
        passed               BOOLEAN NOT NULL,
        blocking_rule_ids    JSONB NOT NULL DEFAULT '[]',
        rule_versions        JSONB NOT NULL DEFAULT '{}',
        evaluated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_gate_eval_tenant_time "
        "ON gate_evaluation_records (tenant_id, evaluated_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_gate_eval_session "
        "ON gate_evaluation_records (session_id, stage_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS gate_evaluation_records CASCADE")
