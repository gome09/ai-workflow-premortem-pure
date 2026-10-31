"""Context digest for save() write-amplification guard.

Revision ID: V010
Revises: V009
Create Date: 2026-10-31

Changes
-------
1. sessions.context_digest — 上一次 save() 写入的上下文内容指纹。
   指纹未变化时 save() 只推进版本与状态，不再重写整份 context_json。
"""

from __future__ import annotations

from alembic import op

revision = "V010"
down_revision = "V009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS context_digest TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS context_digest")
