"""P1 governance hardening: workspace invitations, eval case and run bindings.

Revision ID: V012
Revises: V011
Create Date: 2026-11-01

Changes
-------
1. workspace_invitations — admin-created, token-hash based same-tenant invites.
2. eval_cases.standard_version — monotonic standard revision for immutable run binding.
3. eval_runs.case_version_digest — the exact EvalCase definition a run was executed against.
4. eval_runs.target_deployment_version — the declared target deployment version at run time.
"""

from __future__ import annotations

from alembic import op

revision = "V012"
down_revision = "V011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workspace_invitations (
            invitation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
            email TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer',
            token_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            invited_by UUID,
            expires_at TIMESTAMPTZ NOT NULL,
            accepted_at TIMESTAMPTZ,
            accepted_user_id UUID REFERENCES users(user_id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT workspace_invitations_role_check
                CHECK (role IN ('viewer', 'editor', 'admin')),
            CONSTRAINT workspace_invitations_status_check
                CHECK (status IN ('pending', 'accepted', 'revoked', 'expired'))
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_workspace_invitations_token_hash "
        "ON workspace_invitations (token_hash)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_workspace_invitations_tenant_status "
        "ON workspace_invitations (tenant_id, status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_workspace_invitations_tenant_email "
        "ON workspace_invitations (tenant_id, email)"
    )
    op.execute(
        "ALTER TABLE eval_cases ADD COLUMN IF NOT EXISTS standard_version "
        "INTEGER NOT NULL DEFAULT 1"
    )
    op.execute(
        "ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS case_version_digest "
        "TEXT NOT NULL DEFAULT ''"
    )
    op.execute(
        "ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS target_deployment_version "
        "TEXT NOT NULL DEFAULT ''"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE eval_runs DROP COLUMN IF EXISTS target_deployment_version")
    op.execute("ALTER TABLE eval_runs DROP COLUMN IF EXISTS case_version_digest")
    op.execute("ALTER TABLE eval_cases DROP COLUMN IF EXISTS standard_version")
    op.execute("DROP TABLE IF EXISTS workspace_invitations")
