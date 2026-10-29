"""Query and write-path optimization for multi-tenant PostgreSQL.

Revision ID: V008
Revises: V007
Create Date: 2026-10-27

Changes
-------
1. sessions.version             — optimistic-lock counter.
2. sessions generated columns   — JSONB projections used by list/governance queries.
3. Compound indexes             — tenant-scoped listing and governance filters.
4. human_actions.tenant_id       — backfill from sessions.
5. interrupt_records.stage_id    — TEXT -> INTEGER.
6. Status CHECK constraints      — NOT VALID so historical rows never block migration.
7. sessions.tenant_id -> tenants — NOT VALID foreign key.
"""

from __future__ import annotations

from alembic import op

revision = "V008"
down_revision = "V007"
branch_labels = None
depends_on = None

# Generated-column name -> JSONB expression. jsonb ->> text is immutable, so STORED
# generated columns are allowed by PostgreSQL.
_GENERATED_COLUMNS: dict[str, str] = {
    "data_classification": "context_json->>'data_classification'",
    "selected_scenario_id": "context_json->>'selected_scenario_id'",
    "session_name": "context_json->>'session_name'",
    "scenario_name": "context_json->>'scenario_name'",
    "research_target": "context_json->>'research_target'",
    "domain": "context_json->>'domain'",
}

_CHECK_CONSTRAINTS: tuple[tuple[str, str, str], ...] = (
    (
        "human_actions_status_check",
        "human_actions",
        "status IN ('pending', 'resolved', 'cancelled', 'superseded', 'stale')",
    ),
    (
        "eval_runs_status_check",
        "eval_runs",
        "status IN ('created', 'running', 'completed', 'failed')",
    ),
    (
        "redteam_cases_status_check",
        "redteam_cases",
        "status IS NULL OR status IN ('draft', 'approved', 'rejected', 'synced_to_eval')",
    ),
    (
        "interrupt_records_status_check",
        "interrupt_records",
        "status IS NULL OR status IN ('pending', 'resumed', 'cancelled')",
    ),
)


def upgrade() -> None:
    # ── 1. Optimistic lock ────────────────────────────────────────────────────
    op.execute("ALTER TABLE sessions ADD COLUMN IF NOT EXISTS version BIGINT NOT NULL DEFAULT 0")

    # ── 2. Generated columns ──────────────────────────────────────────────────
    for name, expression in _GENERATED_COLUMNS.items():
        op.execute(
            f"ALTER TABLE sessions ADD COLUMN IF NOT EXISTS {name} TEXT "
            f"GENERATED ALWAYS AS ({expression}) STORED"
        )

    # ── 3. Indexes ────────────────────────────────────────────────────────────
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_tenant_updated "
        "ON sessions (tenant_id, updated_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_tenant_classification "
        "ON sessions (tenant_id, data_classification, selected_scenario_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_tenant ON users (tenant_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_human_actions_session_tenant_status "
        "ON human_actions (session_id, tenant_id, status)"
    )

    # ── 4. Backfill human_actions tenant ownership ────────────────────────────
    op.execute(
        "UPDATE human_actions AS h SET tenant_id = s.tenant_id "
        "FROM sessions AS s "
        "WHERE h.session_id = s.session_id AND h.tenant_id IS NULL"
    )

    # ── 5. interrupt_records.stage_id: TEXT -> INTEGER ────────────────────────
    op.execute("""
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'interrupt_records'
              AND column_name = 'stage_id'
              AND data_type = 'text'
        ) THEN
            ALTER TABLE interrupt_records
                ALTER COLUMN stage_id TYPE INTEGER
                USING CASE
                    WHEN stage_id ~ '^[0-9]+$' THEN stage_id::integer
                    ELSE NULL
                END;
        END IF;
    END $$;
    """)

    # ── 6. Status CHECK constraints (NOT VALID) ───────────────────────────────
    for constraint_name, table_name, expression in _CHECK_CONSTRAINTS:
        # All identifiers and expressions come from module-level constants.
        sql = f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = '{constraint_name}'
                ) THEN
                    ALTER TABLE {table_name}
                        ADD CONSTRAINT {constraint_name}
                        CHECK ({expression}) NOT VALID;
                END IF;
            END $$;
            """  # noqa: S608
        op.execute(sql)

    # ── 7. sessions.tenant_id -> tenants.tenant_id (NOT VALID) ────────────────
    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'fk_sessions_tenant'
        ) THEN
            ALTER TABLE sessions
                ADD CONSTRAINT fk_sessions_tenant
                FOREIGN KEY (tenant_id) REFERENCES tenants (tenant_id)
                NOT VALID;
        END IF;
    END $$;
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE sessions DROP CONSTRAINT IF EXISTS fk_sessions_tenant")
    for constraint_name, table_name, _ in _CHECK_CONSTRAINTS:
        op.execute(f"ALTER TABLE {table_name} DROP CONSTRAINT IF EXISTS {constraint_name}")

    # stage_id back to TEXT (numeric data is preserved as text).
    op.execute("ALTER TABLE interrupt_records ALTER COLUMN stage_id TYPE TEXT USING stage_id::text")

    op.execute("DROP INDEX IF EXISTS idx_human_actions_session_tenant_status")
    op.execute("DROP INDEX IF EXISTS idx_users_tenant")
    op.execute("DROP INDEX IF EXISTS idx_sessions_tenant_classification")
    op.execute("DROP INDEX IF EXISTS idx_sessions_tenant_updated")
    for name in _GENERATED_COLUMNS:
        op.execute(f"ALTER TABLE sessions DROP COLUMN IF EXISTS {name}")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS version")
