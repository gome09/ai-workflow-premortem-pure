"""Business closure: real-target execution metadata on eval_runs.

Revision ID: V011
Revises: V010
Create Date: 2026-11-01

Changes
-------
1. eval_runs.execution_kind — 模拟执行 / 平台模型执行 / 真实目标执行区分。
2. eval_runs.execution_outcome — 真实目标的 success/failed/timeout/error。
3. eval_runs.evaluation_version_digest — 该 run 绑定的评估版本。
4. eval_runs.target_endpoint — 脱敏后的真实目标 endpoint（非 target 模式为空）。
"""

from __future__ import annotations

from alembic import op

revision = "V011"
down_revision = "V010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS execution_kind "
        "TEXT NOT NULL DEFAULT 'manual_simulation'"
    )
    op.execute("ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS execution_outcome TEXT")
    op.execute(
        "ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS evaluation_version_digest "
        "TEXT NOT NULL DEFAULT ''"
    )
    op.execute(
        "ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS target_endpoint TEXT NOT NULL DEFAULT ''"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE eval_runs DROP COLUMN IF EXISTS target_endpoint")
    op.execute("ALTER TABLE eval_runs DROP COLUMN IF EXISTS evaluation_version_digest")
    op.execute("ALTER TABLE eval_runs DROP COLUMN IF EXISTS execution_outcome")
    op.execute("ALTER TABLE eval_runs DROP COLUMN IF EXISTS execution_kind")
