"""Schema alignment: sync PostgreSQL DDL with current business-code expectations.

Revision ID: V003
Revises: V002
Create Date: 2026-06-08

Changes
-------
1. human_actions    — ADD 12 columns missing from V001
2. llm_traces       — ADD 6 columns missing from V001
3. redteam_cases    — ADD new columns, DROP obsolete V001 columns
4. action_resolution_logs  — CREATE TABLE (missing from V001/V002)
5. eval_judgments           — CREATE TABLE (missing from V001/V002)
6. human_calibrations       — CREATE TABLE (missing from V001/V002)
7. interrupt_records        — CREATE TABLE (missing from V001/V002)

All ADD COLUMN / DROP COLUMN use IF NOT EXISTS / IF EXISTS for idempotency.
"""

from __future__ import annotations

from alembic import op

revision = "V003"
down_revision = "V002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. human_actions: add 12 missing columns ──────────────────────────────
    op.execute("ALTER TABLE human_actions ADD COLUMN IF NOT EXISTS action_contract_id    TEXT")
    op.execute("ALTER TABLE human_actions ADD COLUMN IF NOT EXISTS action_schema_version TEXT")
    op.execute("ALTER TABLE human_actions ADD COLUMN IF NOT EXISTS idempotency_key       TEXT")
    op.execute("ALTER TABLE human_actions ADD COLUMN IF NOT EXISTS target_stage          INT")
    op.execute("ALTER TABLE human_actions ADD COLUMN IF NOT EXISTS target_stage_version  INT")
    op.execute("ALTER TABLE human_actions ADD COLUMN IF NOT EXISTS target_object_path    TEXT")
    op.execute("ALTER TABLE human_actions ADD COLUMN IF NOT EXISTS expected_before_hash  TEXT")
    op.execute("ALTER TABLE human_actions ADD COLUMN IF NOT EXISTS approved_payload_hash TEXT")
    op.execute("ALTER TABLE human_actions ADD COLUMN IF NOT EXISTS resume_token          TEXT")
    op.execute(
        "ALTER TABLE human_actions ADD COLUMN IF NOT EXISTS expires_at            TIMESTAMPTZ"
    )
    op.execute("ALTER TABLE human_actions ADD COLUMN IF NOT EXISTS resolution_attempts   INT")
    op.execute("ALTER TABLE human_actions ADD COLUMN IF NOT EXISTS last_resolution_error TEXT")

    # ── 2. llm_traces: add 6 missing columns ──────────────────────────────────
    op.execute("ALTER TABLE llm_traces ADD COLUMN IF NOT EXISTS provider                 TEXT")
    op.execute("ALTER TABLE llm_traces ADD COLUMN IF NOT EXISTS prompt_template_id       TEXT")
    op.execute("ALTER TABLE llm_traces ADD COLUMN IF NOT EXISTS prompt_template_version  TEXT")
    op.execute("ALTER TABLE llm_traces ADD COLUMN IF NOT EXISTS retry_count              INT")
    op.execute("ALTER TABLE llm_traces ADD COLUMN IF NOT EXISTS evidence_count           INT")
    op.execute("ALTER TABLE llm_traces ADD COLUMN IF NOT EXISTS error_message            TEXT")

    # ── 3. redteam_cases: migrate from V001 structure to current structure ─────
    # Add new columns
    op.execute("ALTER TABLE redteam_cases ADD COLUMN IF NOT EXISTS target_node_id          TEXT")
    op.execute("ALTER TABLE redteam_cases ADD COLUMN IF NOT EXISTS source_finding_id       TEXT")
    op.execute("ALTER TABLE redteam_cases ADD COLUMN IF NOT EXISTS source_failure_mode_id  TEXT")
    op.execute("ALTER TABLE redteam_cases ADD COLUMN IF NOT EXISTS attack_type             TEXT")
    op.execute("ALTER TABLE redteam_cases ADD COLUMN IF NOT EXISTS severity                TEXT")
    op.execute("ALTER TABLE redteam_cases ADD COLUMN IF NOT EXISTS status                  TEXT")
    op.execute("ALTER TABLE redteam_cases ADD COLUMN IF NOT EXISTS linked_eval_case_id     TEXT")
    op.execute(
        "ALTER TABLE redteam_cases ADD COLUMN IF NOT EXISTS taxonomy_refs JSONB NOT NULL DEFAULT '[]'"
    )
    op.execute(
        "ALTER TABLE redteam_cases ADD COLUMN IF NOT EXISTS control_refs  JSONB NOT NULL DEFAULT '{}'"
    )
    op.execute(
        "ALTER TABLE redteam_cases ADD COLUMN IF NOT EXISTS payload_json  JSONB NOT NULL DEFAULT '{}'"
    )
    op.execute("ALTER TABLE redteam_cases ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ")
    op.execute("ALTER TABLE redteam_cases ADD COLUMN IF NOT EXISTS updated_at  TIMESTAMPTZ")

    # Drop obsolete V001 columns (safe — no business code reads them)
    op.execute("ALTER TABLE redteam_cases DROP COLUMN IF EXISTS category")
    op.execute("ALTER TABLE redteam_cases DROP COLUMN IF EXISTS attack_vector")
    op.execute("ALTER TABLE redteam_cases DROP COLUMN IF EXISTS input_payload")
    op.execute("ALTER TABLE redteam_cases DROP COLUMN IF EXISTS expected_block")
    op.execute("ALTER TABLE redteam_cases DROP COLUMN IF EXISTS actual_output")
    op.execute("ALTER TABLE redteam_cases DROP COLUMN IF EXISTS blocked")
    op.execute("ALTER TABLE redteam_cases DROP COLUMN IF EXISTS score")

    # ── 4. action_resolution_logs ─────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS action_resolution_logs (
        log_id           TEXT PRIMARY KEY,
        session_id       TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        action_id        TEXT NOT NULL,
        idempotency_key  TEXT,
        requested_status TEXT,
        result_status    TEXT,
        before_hash      TEXT,
        after_hash       TEXT,
        error_message    TEXT,
        created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_action_resolution_logs_session "
        "ON action_resolution_logs (session_id, action_id)"
    )

    # ── 5. eval_judgments ─────────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS eval_judgments (
        judgment_id   TEXT PRIMARY KEY,
        session_id    TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        eval_run_id   TEXT,
        eval_id       TEXT,
        experiment_id TEXT,
        judge_type    TEXT,
        judge_model   TEXT,
        score         DOUBLE PRECISION,
        label         TEXT,
        rationale     TEXT,
        uncertainty   DOUBLE PRECISION,
        cited_rules   JSONB NOT NULL DEFAULT '[]',
        payload_json  JSONB NOT NULL DEFAULT '{}',
        created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_eval_judgments_session ON eval_judgments (session_id)"
    )

    # ── 6. human_calibrations ─────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS human_calibrations (
        calibration_id      TEXT PRIMARY KEY,
        session_id          TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        eval_run_id         TEXT,
        eval_id             TEXT,
        experiment_id       TEXT,
        human_label         TEXT,
        human_comment       TEXT,
        judge_label         TEXT,
        agreement           BOOLEAN,
        disagreement_reason TEXT,
        reviewer_id         TEXT,
        payload_json        JSONB NOT NULL DEFAULT '{}',
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_human_calibrations_session "
        "ON human_calibrations (session_id)"
    )

    # ── 7. interrupt_records ──────────────────────────────────────────────────
    op.execute("""
    CREATE TABLE IF NOT EXISTS interrupt_records (
        interrupt_id         TEXT PRIMARY KEY,
        session_id           TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        action_id            TEXT,
        stage_id             TEXT,
        stage_output_version INT,
        status               TEXT,
        resume_value         JSONB,
        thread_id            TEXT,
        node_name            TEXT,
        checkpoint_ns        TEXT,
        interrupt_payload    JSONB,
        resume_consumed_at   TIMESTAMPTZ,
        created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        resolved_at          TIMESTAMPTZ
    )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_interrupt_records_session ON interrupt_records (session_id)"
    )


def downgrade() -> None:
    # Drop new tables
    for table in (
        "interrupt_records",
        "human_calibrations",
        "eval_judgments",
        "action_resolution_logs",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

    # Restore redteam_cases obsolete columns (data cannot be recovered)
    op.execute("ALTER TABLE redteam_cases DROP COLUMN IF EXISTS target_node_id")
    op.execute("ALTER TABLE redteam_cases DROP COLUMN IF EXISTS source_finding_id")
    op.execute("ALTER TABLE redteam_cases DROP COLUMN IF EXISTS source_failure_mode_id")
    op.execute("ALTER TABLE redteam_cases DROP COLUMN IF EXISTS attack_type")
    op.execute("ALTER TABLE redteam_cases DROP COLUMN IF EXISTS severity")
    op.execute("ALTER TABLE redteam_cases DROP COLUMN IF EXISTS status")
    op.execute("ALTER TABLE redteam_cases DROP COLUMN IF EXISTS linked_eval_case_id")
    op.execute("ALTER TABLE redteam_cases DROP COLUMN IF EXISTS taxonomy_refs")
    op.execute("ALTER TABLE redteam_cases DROP COLUMN IF EXISTS control_refs")
    op.execute("ALTER TABLE redteam_cases DROP COLUMN IF EXISTS payload_json")
    op.execute("ALTER TABLE redteam_cases DROP COLUMN IF EXISTS approved_at")
    op.execute("ALTER TABLE redteam_cases DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE redteam_cases ADD COLUMN IF NOT EXISTS category       TEXT")
    op.execute("ALTER TABLE redteam_cases ADD COLUMN IF NOT EXISTS attack_vector  TEXT")
    op.execute(
        "ALTER TABLE redteam_cases ADD COLUMN IF NOT EXISTS input_payload  TEXT NOT NULL DEFAULT ''"
    )
    op.execute(
        "ALTER TABLE redteam_cases ADD COLUMN IF NOT EXISTS expected_block BOOLEAN NOT NULL DEFAULT TRUE"
    )
    op.execute("ALTER TABLE redteam_cases ADD COLUMN IF NOT EXISTS actual_output  TEXT")
    op.execute("ALTER TABLE redteam_cases ADD COLUMN IF NOT EXISTS blocked        BOOLEAN")
    op.execute("ALTER TABLE redteam_cases ADD COLUMN IF NOT EXISTS score          INT")

    # Remove added llm_traces columns
    op.execute("ALTER TABLE llm_traces DROP COLUMN IF EXISTS provider")
    op.execute("ALTER TABLE llm_traces DROP COLUMN IF EXISTS prompt_template_id")
    op.execute("ALTER TABLE llm_traces DROP COLUMN IF EXISTS prompt_template_version")
    op.execute("ALTER TABLE llm_traces DROP COLUMN IF EXISTS retry_count")
    op.execute("ALTER TABLE llm_traces DROP COLUMN IF EXISTS evidence_count")
    op.execute("ALTER TABLE llm_traces DROP COLUMN IF EXISTS error_message")

    # Remove added human_actions columns
    op.execute("ALTER TABLE human_actions DROP COLUMN IF EXISTS action_contract_id")
    op.execute("ALTER TABLE human_actions DROP COLUMN IF EXISTS action_schema_version")
    op.execute("ALTER TABLE human_actions DROP COLUMN IF EXISTS idempotency_key")
    op.execute("ALTER TABLE human_actions DROP COLUMN IF EXISTS target_stage")
    op.execute("ALTER TABLE human_actions DROP COLUMN IF EXISTS target_stage_version")
    op.execute("ALTER TABLE human_actions DROP COLUMN IF EXISTS target_object_path")
    op.execute("ALTER TABLE human_actions DROP COLUMN IF EXISTS expected_before_hash")
    op.execute("ALTER TABLE human_actions DROP COLUMN IF EXISTS approved_payload_hash")
    op.execute("ALTER TABLE human_actions DROP COLUMN IF EXISTS resume_token")
    op.execute("ALTER TABLE human_actions DROP COLUMN IF EXISTS expires_at")
    op.execute("ALTER TABLE human_actions DROP COLUMN IF EXISTS resolution_attempts")
    op.execute("ALTER TABLE human_actions DROP COLUMN IF EXISTS last_resolution_error")
