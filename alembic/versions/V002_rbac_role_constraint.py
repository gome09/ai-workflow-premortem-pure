"""RBAC role constraint: enforce viewer/editor/admin values, set default to viewer

Revision ID: V002
Revises: V001
Create Date: 2026-06-03
"""

from __future__ import annotations

from alembic import op

revision = "V002"
down_revision = "V001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE users
            ALTER COLUMN role SET DEFAULT 'viewer'
    """)
    # Idempotent: skip if constraint already exists (e.g. partial previous run)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'users_role_check'
                  AND conrelid = 'users'::regclass
            ) THEN
                ALTER TABLE users
                    ADD CONSTRAINT users_role_check
                    CHECK (role IN ('viewer', 'editor', 'admin'));
            END IF;
        END$$;
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check")
    op.execute("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'member'")
