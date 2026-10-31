"""Projection sync state and eval-run contract columns.

Revision ID: V009
Revises: V008
Create Date: 2026-10-31

Changes
-------
1. sessions.projection_state — 上一次 save() 的投影集合状态（哈希 / 追加游标）。
2. eval_runs.pass_criteria / llm_judge_suggestion — 与 EvalRun 模型对齐，
   使 eval_runs 投影直读能返回完整字段。
"""

from __future__ import annotations

from alembic import op

revision = "V009"
down_revision = "V008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS projection_state JSONB NOT NULL DEFAULT '{}'"
    )
    op.execute(
        "ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS pass_criteria JSONB NOT NULL DEFAULT '[]'"
    )
    op.execute("ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS llm_judge_suggestion JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE eval_runs DROP COLUMN IF EXISTS llm_judge_suggestion")
    op.execute("ALTER TABLE eval_runs DROP COLUMN IF EXISTS pass_criteria")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS projection_state")
