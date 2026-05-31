# storage/migrations/registry.py
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

MIGRATIONS: list[tuple[str, str]] = [
    (
        "v070_001_action_contract_and_logs",
        """
        ALTER TABLE human_actions ADD COLUMN IF NOT EXISTS action_contract_id TEXT;
        ALTER TABLE human_actions ADD COLUMN IF NOT EXISTS action_schema_version TEXT NOT NULL DEFAULT '0.7.0';
        ALTER TABLE human_actions ADD COLUMN IF NOT EXISTS idempotency_key TEXT;
        ALTER TABLE human_actions ADD COLUMN IF NOT EXISTS target_stage INT;
        ALTER TABLE human_actions ADD COLUMN IF NOT EXISTS target_stage_version INT;
        ALTER TABLE human_actions ADD COLUMN IF NOT EXISTS target_object_path TEXT;
        ALTER TABLE human_actions ADD COLUMN IF NOT EXISTS expected_before_hash TEXT;
        ALTER TABLE human_actions ADD COLUMN IF NOT EXISTS approved_payload_hash TEXT;
        ALTER TABLE human_actions ADD COLUMN IF NOT EXISTS resume_token TEXT;
        ALTER TABLE human_actions ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
        ALTER TABLE human_actions ADD COLUMN IF NOT EXISTS resolution_attempts INT NOT NULL DEFAULT 0;
        ALTER TABLE human_actions ADD COLUMN IF NOT EXISTS last_resolution_error TEXT;

        CREATE TABLE IF NOT EXISTS action_resolution_logs (
            log_id             TEXT PRIMARY KEY,
            session_id         TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
            action_id          TEXT NOT NULL,
            idempotency_key    TEXT,
            requested_status   TEXT NOT NULL,
            result_status      TEXT NOT NULL,
            before_hash        TEXT,
            after_hash         TEXT,
            error_message      TEXT,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_action_resolution_logs_session_action
            ON action_resolution_logs (session_id, action_id, created_at DESC);
        """,
    ),
    (
        "v070_002_llm_traces",
        """
        CREATE TABLE IF NOT EXISTS llm_traces (
            trace_id                 TEXT PRIMARY KEY,
            session_id               TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
            stage                    INT,
            node_name                TEXT NOT NULL DEFAULT '',
            provider                 TEXT NOT NULL DEFAULT 'openai_compatible',
            model                    TEXT NOT NULL DEFAULT '',
            prompt_template_id       TEXT NOT NULL DEFAULT '',
            prompt_template_version  TEXT NOT NULL DEFAULT '',
            input_token_count        INT,
            output_token_count       INT,
            estimated_cost           DOUBLE PRECISION,
            latency_ms               INT,
            retry_count              INT NOT NULL DEFAULT 0,
            parser_status            TEXT NOT NULL DEFAULT '',
            safety_status            TEXT NOT NULL DEFAULT '',
            evidence_count           INT NOT NULL DEFAULT 0,
            error_type               TEXT,
            error_message            TEXT,
            created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_llm_traces_session_created
            ON llm_traces (session_id, created_at DESC);
        """,
    ),
    (
        "v070_003_trace_metadata_and_stale_actions",
        """
        ALTER TABLE llm_traces ADD COLUMN IF NOT EXISTS trace_type TEXT NOT NULL DEFAULT 'llm';
        ALTER TABLE llm_traces ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}';
        ALTER TABLE human_actions ADD COLUMN IF NOT EXISTS last_resolution_error TEXT;
        """,
    ),
    (
        "v080_001_eval_dataset_experiment_foundation",
        """
        ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS dataset_id TEXT;
        ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS experiment_id TEXT;
        ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS run_index INT;
        ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS trace_id TEXT;
        ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS latency_ms INT;
        ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS estimated_cost DOUBLE PRECISION;

        CREATE INDEX IF NOT EXISTS idx_eval_runs_experiment
            ON eval_runs (session_id, experiment_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS eval_datasets (
            dataset_id      TEXT PRIMARY KEY,
            session_id      TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
            name            TEXT NOT NULL,
            version         TEXT NOT NULL,
            source          TEXT,
            stage           INT,
            scenario_type   TEXT,
            case_ids        JSONB NOT NULL DEFAULT '[]',
            payload_json    JSONB NOT NULL DEFAULT '{}',
            created_at      TIMESTAMPTZ,
            updated_at      TIMESTAMPTZ
        );

        CREATE INDEX IF NOT EXISTS idx_eval_datasets_session
            ON eval_datasets (session_id, created_at DESC);

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
        );

        CREATE INDEX IF NOT EXISTS idx_eval_experiments_session
            ON eval_experiments (session_id, dataset_id, created_at DESC);
        """,
    ),
    (
        "v080_003_redteam_foundation",
        """
        CREATE TABLE IF NOT EXISTS redteam_cases (
            redteam_case_id       TEXT PRIMARY KEY,
            session_id            TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
            target_stage          INT NOT NULL DEFAULT 3,
            target_node_id        TEXT,
            source_finding_id     TEXT,
            source_failure_mode_id TEXT,
            attack_type           TEXT NOT NULL,
            severity              TEXT NOT NULL,
            status                TEXT NOT NULL,
            linked_eval_case_id   TEXT,
            payload_json          JSONB NOT NULL DEFAULT '{}',
            created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            approved_at           TIMESTAMPTZ,
            updated_at            TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS idx_redteam_cases_session_status
            ON redteam_cases (session_id, status, severity);
        CREATE INDEX IF NOT EXISTS idx_redteam_cases_target
            ON redteam_cases (session_id, target_stage, target_node_id);
        """,
    ),
    (
        "v080_004_taxonomy_mapping",
        """
        ALTER TABLE safety_findings ADD COLUMN IF NOT EXISTS taxonomy_refs JSONB NOT NULL DEFAULT '[]';
        ALTER TABLE safety_findings ADD COLUMN IF NOT EXISTS control_refs JSONB NOT NULL DEFAULT '[]';
        ALTER TABLE safety_findings ADD COLUMN IF NOT EXISTS mitigation_status TEXT NOT NULL DEFAULT 'open';
        ALTER TABLE safety_findings ADD COLUMN IF NOT EXISTS residual_risk TEXT NOT NULL DEFAULT 'unknown';

        ALTER TABLE redteam_cases ADD COLUMN IF NOT EXISTS taxonomy_refs JSONB NOT NULL DEFAULT '[]';
        ALTER TABLE redteam_cases ADD COLUMN IF NOT EXISTS control_refs JSONB NOT NULL DEFAULT '[]';
        """,
    ),
    (
        "v080_005_eval_judgment_calibration",
        """
        CREATE TABLE IF NOT EXISTS eval_judgments (
            judgment_id      TEXT PRIMARY KEY,
            session_id       TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
            eval_run_id      TEXT NOT NULL,
            eval_id          TEXT,
            experiment_id    TEXT,
            judge_type       TEXT NOT NULL,
            judge_model      TEXT,
            score            DOUBLE PRECISION,
            label            TEXT NOT NULL,
            rationale        TEXT NOT NULL DEFAULT '',
            uncertainty      DOUBLE PRECISION,
            cited_rules      JSONB NOT NULL DEFAULT '[]',
            payload_json     JSONB NOT NULL DEFAULT '{}',
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_eval_judgments_session_run
            ON eval_judgments (session_id, eval_run_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS human_calibrations (
            calibration_id       TEXT PRIMARY KEY,
            session_id           TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
            eval_run_id          TEXT NOT NULL,
            eval_id              TEXT,
            experiment_id        TEXT,
            human_label          TEXT NOT NULL,
            human_comment        TEXT NOT NULL DEFAULT '',
            judge_label          TEXT,
            agreement            BOOLEAN,
            disagreement_reason  TEXT NOT NULL DEFAULT '',
            reviewer_id          TEXT NOT NULL DEFAULT 'human_reviewer',
            payload_json         JSONB NOT NULL DEFAULT '{}',
            created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_human_calibrations_session_run
            ON human_calibrations (session_id, eval_run_id, created_at DESC);
        """,
    ),
    (
        "v080_006_trace_backfill",
        """
        ALTER TABLE eval_cases ADD COLUMN IF NOT EXISTS source_type TEXT NOT NULL DEFAULT 'stage3_generated';
        ALTER TABLE eval_cases ADD COLUMN IF NOT EXISTS source_trace_id TEXT;
        ALTER TABLE eval_cases ADD COLUMN IF NOT EXISTS source_ref_id TEXT;
        ALTER TABLE eval_cases ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}';
        CREATE INDEX IF NOT EXISTS idx_eval_cases_source_trace
            ON eval_cases (session_id, source_trace_id);
        """,
    ),
]


def run_storage_migrations(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_id TEXT PRIMARY KEY,
            applied_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    applied_rows = conn.execute("SELECT migration_id FROM schema_migrations").fetchall()
    applied = {row["migration_id"] for row in applied_rows}
    for migration_id, sql in MIGRATIONS:
        if migration_id in applied:
            continue
        conn.execute(sql)
        conn.execute(
            "INSERT INTO schema_migrations (migration_id) VALUES (%s) ON CONFLICT DO NOTHING",
            (migration_id,),
        )
        logger.info("Applied storage migration %s", migration_id)
