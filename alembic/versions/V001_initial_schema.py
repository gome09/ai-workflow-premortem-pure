"""Initial schema — all tables from session_store.py CREATE_TABLES_SQL

Revision ID: V001
Revises:
Create Date: 2026-06-03
"""

from __future__ import annotations

from alembic import op

revision = "V001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        session_id      TEXT PRIMARY KEY,
        current_state   TEXT NOT NULL DEFAULT 'init',
        context_json    JSONB NOT NULL DEFAULT '{}',
        tenant_id       UUID,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_sessions_state ON sessions (current_state)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions (updated_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sessions_tenant ON sessions (tenant_id)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS session_events (
        event_id    BIGSERIAL PRIMARY KEY,
        session_id  TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        event_type  TEXT NOT NULL,
        stage       INT,
        payload     JSONB NOT NULL DEFAULT '{}',
        tenant_id   UUID,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_session ON session_events (session_id, created_at DESC)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_session_events_tenant ON session_events (tenant_id)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS human_actions (
        action_id             TEXT PRIMARY KEY,
        session_id            TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        stage_id              INT NOT NULL,
        node_id               TEXT,
        source_type           TEXT,
        source_id             TEXT,
        action_type           TEXT NOT NULL,
        status                TEXT NOT NULL DEFAULT 'pending',
        risk_level            TEXT NOT NULL DEFAULT 'medium',
        title                 TEXT NOT NULL,
        description           TEXT NOT NULL,
        trigger_reason        TEXT,
        blocking              BOOLEAN NOT NULL DEFAULT TRUE,
        payload_before        JSONB NOT NULL DEFAULT '{}',
        payload_after         JSONB,
        reviewer_decision     TEXT,
        reviewer_note         TEXT,
        stage_output_version  INT NOT NULL DEFAULT 1,
        superseded_by         TEXT,
        tenant_id             UUID,
        created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        resolved_at           TIMESTAMPTZ
    )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_human_actions_session_status ON human_actions (session_id, status, stage_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_human_actions_stage_version ON human_actions (session_id, stage_id, stage_output_version, status)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_human_actions_tenant ON human_actions (tenant_id)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS audit_events (
        event_id        TEXT PRIMARY KEY,
        session_id      TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        actor           TEXT NOT NULL,
        event_type      TEXT NOT NULL,
        target_type     TEXT NOT NULL,
        target_id       TEXT NOT NULL,
        before_hash     TEXT,
        after_hash      TEXT,
        before_snapshot JSONB,
        after_snapshot  JSONB,
        metadata        JSONB NOT NULL DEFAULT '{}',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_events_session_created ON audit_events (session_id, created_at DESC)"
    )

    op.execute("""
    CREATE TABLE IF NOT EXISTS evidence_sources (
        evidence_id              TEXT PRIMARY KEY,
        session_id               TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        title                    TEXT NOT NULL,
        url                      TEXT,
        source_type              TEXT NOT NULL,
        credibility_score        DOUBLE PRECISION NOT NULL DEFAULT 0,
        summary                  TEXT,
        claims                   JSONB NOT NULL DEFAULT '[]',
        used_by_failure_mode_ids JSONB NOT NULL DEFAULT '[]',
        verified                 BOOLEAN NOT NULL DEFAULT FALSE,
        verified_by              TEXT,
        verified_at              TIMESTAMPTZ,
        verification_note        TEXT,
        retrieved_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_evidence_sources_session ON evidence_sources (session_id, credibility_score DESC)"
    )

    op.execute("""
    CREATE TABLE IF NOT EXISTS safety_findings (
        finding_id            TEXT PRIMARY KEY,
        session_id            TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        stage_id              INT,
        risk_type             TEXT NOT NULL,
        severity              TEXT NOT NULL,
        location              TEXT NOT NULL,
        description           TEXT NOT NULL,
        recommended_action    TEXT NOT NULL,
        requires_human_review BOOLEAN NOT NULL DEFAULT FALSE,
        status                TEXT NOT NULL DEFAULT 'open',
        taxonomy_refs         JSONB NOT NULL DEFAULT '[]',
        control_refs          JSONB NOT NULL DEFAULT '[]',
        mitigation_status     TEXT NOT NULL DEFAULT 'open',
        residual_risk         TEXT NOT NULL DEFAULT 'unknown',
        resolution_note       TEXT NOT NULL DEFAULT '',
        resolved_at           TIMESTAMPTZ,
        created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_safety_findings_session ON safety_findings (session_id, status, severity)"
    )

    op.execute("""
    CREATE TABLE IF NOT EXISTS report_artifacts (
        report_id        TEXT PRIMARY KEY,
        session_id       TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        version          TEXT NOT NULL,
        content_json     JSONB NOT NULL DEFAULT '{}',
        content_markdown TEXT NOT NULL DEFAULT '',
        generated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_report_artifacts_session ON report_artifacts (session_id, generated_at DESC)"
    )

    op.execute("""
    CREATE TABLE IF NOT EXISTS eval_cases (
        eval_id                  TEXT PRIMARY KEY,
        session_id               TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        stage_id                 INT NOT NULL DEFAULT 3,
        target_node_id           TEXT,
        covered_failure_mode_ids JSONB NOT NULL DEFAULT '[]',
        scenario_type            TEXT NOT NULL,
        source_type              TEXT NOT NULL DEFAULT 'stage3_generated',
        source_trace_id          TEXT,
        source_ref_id            TEXT,
        metadata                 JSONB NOT NULL DEFAULT '{}',
        input_payload            TEXT NOT NULL,
        expected_behavior        TEXT NOT NULL,
        pass_criteria            JSONB NOT NULL DEFAULT '[]',
        actual_output            TEXT,
        human_score              INT,
        human_comment            TEXT,
        passed                   BOOLEAN,
        created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        scored_at                TIMESTAMPTZ
    )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_eval_cases_session ON eval_cases (session_id, stage_id, scenario_type)"
    )

    op.execute("""
    CREATE TABLE IF NOT EXISTS eval_runs (
        run_id                   TEXT PRIMARY KEY,
        session_id               TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        eval_id                  TEXT NOT NULL,
        target_node_id           TEXT,
        covered_failure_mode_ids JSONB NOT NULL DEFAULT '[]',
        stage_output_version     INT NOT NULL DEFAULT 1,
        run_mode                 TEXT NOT NULL,
        input_payload            TEXT NOT NULL,
        expected_behavior        TEXT NOT NULL,
        actual_output            TEXT,
        judge_result             TEXT,
        judge_reason             TEXT NOT NULL DEFAULT '',
        judge_mode               TEXT NOT NULL DEFAULT 'inherited',
        violated_criteria        JSONB NOT NULL DEFAULT '[]',
        status                   TEXT NOT NULL DEFAULT 'created',
        error_message            TEXT NOT NULL DEFAULT '',
        dataset_id               TEXT,
        experiment_id            TEXT,
        run_index                INT,
        trace_id                 TEXT,
        latency_ms               INT,
        estimated_cost           DOUBLE PRECISION,
        created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        completed_at             TIMESTAMPTZ
    )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_eval_runs_session ON eval_runs (session_id, eval_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_eval_runs_experiment ON eval_runs (session_id, experiment_id, created_at DESC)"
    )

    op.execute("""
    CREATE TABLE IF NOT EXISTS eval_datasets (
        dataset_id    TEXT PRIMARY KEY,
        session_id    TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        name          TEXT NOT NULL,
        version       TEXT NOT NULL,
        source        TEXT,
        stage         INT,
        scenario_type TEXT,
        case_ids      JSONB NOT NULL DEFAULT '[]',
        payload_json  JSONB NOT NULL DEFAULT '{}',
        created_at    TIMESTAMPTZ,
        updated_at    TIMESTAMPTZ
    )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_eval_datasets_session ON eval_datasets (session_id, created_at DESC)"
    )

    op.execute("""
    CREATE TABLE IF NOT EXISTS eval_experiments (
        experiment_id          TEXT PRIMARY KEY,
        session_id             TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        dataset_id             TEXT NOT NULL,
        name                   TEXT NOT NULL,
        status                 TEXT NOT NULL,
        run_mode               TEXT,
        provider               TEXT,
        model                  TEXT,
        baseline_experiment_id TEXT,
        eval_ids               JSONB NOT NULL DEFAULT '[]',
        run_ids                JSONB NOT NULL DEFAULT '[]',
        aggregate_metrics      JSONB NOT NULL DEFAULT '{}',
        comparison_summary     JSONB NOT NULL DEFAULT '{}',
        payload_json           JSONB NOT NULL DEFAULT '{}',
        created_at             TIMESTAMPTZ,
        started_at             TIMESTAMPTZ,
        completed_at           TIMESTAMPTZ
    )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_eval_experiments_session ON eval_experiments (session_id, dataset_id, created_at DESC)"
    )

    op.execute("""
    CREATE TABLE IF NOT EXISTS redteam_cases (
        redteam_case_id TEXT PRIMARY KEY,
        session_id      TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        target_stage    INT NOT NULL DEFAULT 3,
        category        TEXT,
        attack_vector   TEXT,
        input_payload   TEXT NOT NULL,
        expected_block  BOOLEAN NOT NULL DEFAULT TRUE,
        actual_output   TEXT,
        blocked         BOOLEAN,
        score           INT,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_redteam_cases_session ON redteam_cases (session_id, target_stage)"
    )

    op.execute("""
    CREATE TABLE IF NOT EXISTS llm_traces (
        trace_id           TEXT PRIMARY KEY,
        session_id         TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
        stage              INT,
        node_name          TEXT,
        trace_type         TEXT,
        model              TEXT,
        input_token_count  INT,
        output_token_count INT,
        estimated_cost     DOUBLE PRECISION,
        latency_ms         INT,
        parser_status      TEXT,
        safety_status      TEXT,
        error_type         TEXT,
        metadata           JSONB NOT NULL DEFAULT '{}',
        created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_llm_traces_session ON llm_traces (session_id, stage, created_at DESC)"
    )

    op.execute("""
    CREATE TABLE IF NOT EXISTS tenants (
        tenant_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name       TEXT NOT NULL,
        created_at TIMESTAMPTZ DEFAULT now()
    )
    """)

    op.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id     UUID NOT NULL REFERENCES tenants(tenant_id),
        email         TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role          TEXT NOT NULL DEFAULT 'viewer',
        created_at    TIMESTAMPTZ DEFAULT now()
    )
    """)


def downgrade() -> None:
    for table in [
        "users",
        "tenants",
        "llm_traces",
        "redteam_cases",
        "eval_experiments",
        "eval_datasets",
        "eval_runs",
        "eval_cases",
        "report_artifacts",
        "safety_findings",
        "evidence_sources",
        "audit_events",
        "human_actions",
        "session_events",
        "sessions",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
