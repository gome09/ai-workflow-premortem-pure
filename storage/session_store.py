# storage/session_store.py
from __future__ import annotations

import json
import logging
from datetime import datetime

import psycopg
from psycopg.rows import dict_row

from core.config import settings
from core.migrations import migrate_context
from core.models import ProjectContext
from storage.migrations import run_storage_migrations

logger = logging.getLogger(__name__)

# ── 建表 SQL ─────────────────────────────────────────────────────────────────

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id      TEXT PRIMARY KEY,
    current_state   TEXT NOT NULL DEFAULT 'init',
    context_json    JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_state
    ON sessions (current_state);

CREATE INDEX IF NOT EXISTS idx_sessions_updated
    ON sessions (updated_at DESC);

CREATE TABLE IF NOT EXISTS session_events (
    event_id        BIGSERIAL PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    event_type      TEXT NOT NULL,
    stage           INT,
    payload         JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_session
    ON session_events (session_id, created_at DESC);

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
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at           TIMESTAMPTZ
);

ALTER TABLE human_actions
    ADD COLUMN IF NOT EXISTS stage_output_version INT NOT NULL DEFAULT 1;
ALTER TABLE human_actions
    ADD COLUMN IF NOT EXISTS superseded_by TEXT;

CREATE INDEX IF NOT EXISTS idx_human_actions_session_status
    ON human_actions (session_id, status, stage_id);

CREATE INDEX IF NOT EXISTS idx_human_actions_stage_version
    ON human_actions (session_id, stage_id, stage_output_version, status);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id      TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    actor         TEXT NOT NULL,
    event_type    TEXT NOT NULL,
    target_type   TEXT NOT NULL,
    target_id     TEXT NOT NULL,
    before_hash   TEXT,
    after_hash    TEXT,
    before_snapshot JSONB,
    after_snapshot  JSONB,
    metadata      JSONB NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_events_session_created
    ON audit_events (session_id, created_at DESC);

ALTER TABLE audit_events
    ADD COLUMN IF NOT EXISTS before_snapshot JSONB;
ALTER TABLE audit_events
    ADD COLUMN IF NOT EXISTS after_snapshot JSONB;

CREATE TABLE IF NOT EXISTS evidence_sources (
    evidence_id                 TEXT PRIMARY KEY,
    session_id                  TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    title                       TEXT NOT NULL,
    url                         TEXT,
    source_type                 TEXT NOT NULL,
    credibility_score           DOUBLE PRECISION NOT NULL DEFAULT 0,
    summary                     TEXT,
    claims                      JSONB NOT NULL DEFAULT '[]',
    used_by_failure_mode_ids    JSONB NOT NULL DEFAULT '[]',
    verified                    BOOLEAN NOT NULL DEFAULT FALSE,
    verified_by                 TEXT,
    verified_at                 TIMESTAMPTZ,
    verification_note           TEXT,
    retrieved_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_evidence_sources_session
    ON evidence_sources (session_id, credibility_score DESC);

CREATE TABLE IF NOT EXISTS safety_findings (
    finding_id              TEXT PRIMARY KEY,
    session_id              TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    stage_id                INT,
    risk_type               TEXT NOT NULL,
    severity                TEXT NOT NULL,
    location                TEXT NOT NULL,
    description             TEXT NOT NULL,
    recommended_action      TEXT NOT NULL,
    requires_human_review   BOOLEAN NOT NULL DEFAULT FALSE,
    status                  TEXT NOT NULL DEFAULT 'open',
    taxonomy_refs           JSONB NOT NULL DEFAULT '[]',
    control_refs            JSONB NOT NULL DEFAULT '[]',
    mitigation_status       TEXT NOT NULL DEFAULT 'open',
    residual_risk           TEXT NOT NULL DEFAULT 'unknown',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_safety_findings_session
    ON safety_findings (session_id, status, severity);

ALTER TABLE safety_findings
    ADD COLUMN IF NOT EXISTS resolution_note TEXT NOT NULL DEFAULT '';
ALTER TABLE safety_findings
    ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ;
ALTER TABLE safety_findings
    ADD COLUMN IF NOT EXISTS taxonomy_refs JSONB NOT NULL DEFAULT '[]';
ALTER TABLE safety_findings
    ADD COLUMN IF NOT EXISTS control_refs JSONB NOT NULL DEFAULT '[]';
ALTER TABLE safety_findings
    ADD COLUMN IF NOT EXISTS mitigation_status TEXT NOT NULL DEFAULT 'open';
ALTER TABLE safety_findings
    ADD COLUMN IF NOT EXISTS residual_risk TEXT NOT NULL DEFAULT 'unknown';

CREATE TABLE IF NOT EXISTS report_artifacts (
    report_id         TEXT PRIMARY KEY,
    session_id        TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    version           TEXT NOT NULL,
    content_json      JSONB NOT NULL DEFAULT '{}',
    content_markdown  TEXT NOT NULL DEFAULT '',
    generated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE report_artifacts
    ADD COLUMN IF NOT EXISTS content_markdown TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_report_artifacts_session
    ON report_artifacts (session_id, generated_at DESC);

CREATE TABLE IF NOT EXISTS eval_cases (
    eval_id           TEXT PRIMARY KEY,
    session_id        TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    stage_id          INT NOT NULL DEFAULT 3,
    target_node_id    TEXT,
    covered_failure_mode_ids JSONB NOT NULL DEFAULT '[]',
    scenario_type     TEXT NOT NULL,
    source_type       TEXT NOT NULL DEFAULT 'stage3_generated',
    source_trace_id   TEXT,
    source_ref_id     TEXT,
    metadata          JSONB NOT NULL DEFAULT '{}',
    input_payload     TEXT NOT NULL,
    expected_behavior TEXT NOT NULL,
    actual_output     TEXT,
    human_score       INT,
    human_comment     TEXT,
    passed            BOOLEAN,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    scored_at         TIMESTAMPTZ
);

ALTER TABLE eval_cases
    ADD COLUMN IF NOT EXISTS covered_failure_mode_ids JSONB NOT NULL DEFAULT '[]';
ALTER TABLE eval_cases
    ADD COLUMN IF NOT EXISTS pass_criteria JSONB NOT NULL DEFAULT '[]';
ALTER TABLE eval_cases
    ADD COLUMN IF NOT EXISTS source_type TEXT NOT NULL DEFAULT 'stage3_generated';
ALTER TABLE eval_cases
    ADD COLUMN IF NOT EXISTS source_trace_id TEXT;
ALTER TABLE eval_cases
    ADD COLUMN IF NOT EXISTS source_ref_id TEXT;
ALTER TABLE eval_cases
    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_eval_cases_session
    ON eval_cases (session_id, stage_id, scenario_type);

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
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at             TIMESTAMPTZ
);

ALTER TABLE eval_runs
    ADD COLUMN IF NOT EXISTS judge_mode TEXT NOT NULL DEFAULT 'inherited';
ALTER TABLE eval_runs
    ADD COLUMN IF NOT EXISTS violated_criteria JSONB NOT NULL DEFAULT '[]';

ALTER TABLE eval_runs
    ADD COLUMN IF NOT EXISTS dataset_id TEXT;
ALTER TABLE eval_runs
    ADD COLUMN IF NOT EXISTS experiment_id TEXT;
ALTER TABLE eval_runs
    ADD COLUMN IF NOT EXISTS run_index INT;
ALTER TABLE eval_runs
    ADD COLUMN IF NOT EXISTS trace_id TEXT;
ALTER TABLE eval_runs
    ADD COLUMN IF NOT EXISTS latency_ms INT;
ALTER TABLE eval_runs
    ADD COLUMN IF NOT EXISTS estimated_cost DOUBLE PRECISION;

CREATE INDEX IF NOT EXISTS idx_eval_runs_session
    ON eval_runs (session_id, eval_id, created_at DESC);
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
    taxonomy_refs         JSONB NOT NULL DEFAULT '[]',
    control_refs          JSONB NOT NULL DEFAULT '[]',
    payload_json          JSONB NOT NULL DEFAULT '{}',
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved_at           TIMESTAMPTZ,
    updated_at            TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_redteam_cases_session_status
    ON redteam_cases (session_id, status, severity);
CREATE INDEX IF NOT EXISTS idx_redteam_cases_target
    ON redteam_cases (session_id, target_stage, target_node_id);

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

CREATE TABLE IF NOT EXISTS interrupt_records (
    interrupt_id          TEXT PRIMARY KEY,
    session_id            TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    action_id             TEXT NOT NULL,
    stage_id              INT NOT NULL,
    stage_output_version  INT NOT NULL DEFAULT 1,
    status                TEXT NOT NULL DEFAULT 'pending',
    resume_value          JSONB,
    thread_id             TEXT,
    node_name             TEXT,
    checkpoint_ns         TEXT,
    interrupt_payload     JSONB,
    resume_consumed_at    TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at           TIMESTAMPTZ
);

ALTER TABLE interrupt_records
    ADD COLUMN IF NOT EXISTS thread_id TEXT;
ALTER TABLE interrupt_records
    ADD COLUMN IF NOT EXISTS node_name TEXT;
ALTER TABLE interrupt_records
    ADD COLUMN IF NOT EXISTS checkpoint_ns TEXT;
ALTER TABLE interrupt_records
    ADD COLUMN IF NOT EXISTS interrupt_payload JSONB;
ALTER TABLE interrupt_records
    ADD COLUMN IF NOT EXISTS resume_consumed_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_interrupt_records_session_status
    ON interrupt_records (session_id, status, stage_id);
CREATE INDEX IF NOT EXISTS idx_interrupt_records_action
    ON interrupt_records (session_id, action_id);

-- v0.6 checkpoint adapter expects one active mapping per human action.
-- Keep this non-unique for backward compatibility with pre-existing alpha data;
-- duplicate prevention is handled in graph.interrupts._ensure_record_for_action.
CREATE INDEX IF NOT EXISTS idx_interrupt_records_session_action_lookup
    ON interrupt_records (session_id, action_id, interrupt_id);
"""


class SessionStore:
    """PostgreSQL 会话持久化"""

    def __init__(self):
        self._dsn = settings.postgres_dsn_sync

    def _get_conn(self) -> psycopg.Connection:
        return psycopg.connect(self._dsn, row_factory=dict_row)

    def initialize(self) -> None:
        """初始化数据库表（应用启动时调用一次）"""
        with self._get_conn() as conn:
            conn.execute(CREATE_TABLES_SQL)
            run_storage_migrations(conn)
            conn.commit()
        logger.info("Database tables initialized.")

    @staticmethod
    def _build_context_json_for_storage(ctx: ProjectContext) -> str:
        """序列化 context_json，截断大字段以避免超过 PostgreSQL JSONB 256MB 限制。

        LLM traces、eval runs、audit events 等已通过 _sync_* 方法写入独立表，
        context_json 只保留摘要信息。
        """
        data = ctx.model_dump(mode="json")

        # Truncate LLM trace metadata — full traces are in llm_traces table
        truncated_traces = []
        for trace in data.get("llm_traces", []):
            meta = trace.get("metadata") or {}
            truncated_traces.append(
                {
                    "trace_id": trace.get("trace_id"),
                    "session_id": trace.get("session_id"),
                    "stage": trace.get("stage"),
                    "node_name": trace.get("node_name"),
                    "trace_type": trace.get("trace_type"),
                    "model": trace.get("model"),
                    "input_token_count": trace.get("input_token_count"),
                    "output_token_count": trace.get("output_token_count"),
                    "estimated_cost": trace.get("estimated_cost"),
                    "latency_ms": trace.get("latency_ms"),
                    "parser_status": trace.get("parser_status"),
                    "safety_status": trace.get("safety_status"),
                    "error_type": trace.get("error_type"),
                    "created_at": trace.get("created_at"),
                    "metadata_keys": list(meta.keys()) if meta else [],
                }
            )
        data["llm_traces"] = truncated_traces

        # Truncate audit event snapshots — full events are in audit_events table
        truncated_audit = []
        for event in data.get("audit_events", []):
            truncated_audit.append(
                {
                    "event_id": event.get("event_id"),
                    "session_id": event.get("session_id"),
                    "actor": event.get("actor"),
                    "event_type": event.get("event_type"),
                    "target_type": event.get("target_type"),
                    "target_id": event.get("target_id"),
                    "created_at": event.get("created_at"),
                    # before_snapshot / after_snapshot / metadata omitted — full data in audit_events table
                }
            )
        data["audit_events"] = truncated_audit

        # Truncate report artifact content — full data is in report_artifacts table
        truncated_reports = []
        for artifact in data.get("report_artifacts", []):
            truncated_reports.append(
                {
                    "report_id": artifact.get("report_id"),
                    "session_id": artifact.get("session_id"),
                    "version": artifact.get("version"),
                    "generated_at": artifact.get("generated_at"),
                    # content_json / content_markdown omitted — full data in report_artifacts table
                }
            )
        data["report_artifacts"] = truncated_reports

        return json.dumps(data, default=str)

    def save(self, ctx: ProjectContext) -> None:
        """创建或更新会话"""
        ctx.updated_at = datetime.utcnow()
        sql = """
            INSERT INTO sessions (session_id, current_state, context_json, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (session_id) DO UPDATE SET
                current_state = EXCLUDED.current_state,
                context_json  = EXCLUDED.context_json,
                updated_at    = EXCLUDED.updated_at
        """
        with self._get_conn() as conn:
            conn.execute(
                sql,
                (
                    ctx.session_id,
                    ctx.current_state.value,
                    self._build_context_json_for_storage(ctx),
                    ctx.created_at,
                    ctx.updated_at,
                ),
            )
            self._sync_human_actions(conn, ctx)
            self._sync_action_resolution_logs(conn, ctx)
            self._sync_llm_traces(conn, ctx)
            self._sync_audit_events(conn, ctx)
            self._sync_evidence_sources(conn, ctx)
            self._sync_safety_findings(conn, ctx)
            self._sync_report_artifacts(conn, ctx)
            self._sync_eval_cases(conn, ctx)
            self._sync_eval_runs(conn, ctx)
            self._sync_eval_judgments(conn, ctx)
            self._sync_human_calibrations(conn, ctx)
            self._sync_eval_datasets(conn, ctx)
            self._sync_eval_experiments(conn, ctx)
            self._sync_redteam_cases(conn, ctx)
            self._sync_interrupt_records(conn, ctx)
            conn.commit()

    def _sync_human_actions(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        """同步 ProjectContext 中的人工动作到索引表。使用 upsert，避免删除历史。"""
        for action in ctx.pending_actions:
            conn.execute(
                """
                INSERT INTO human_actions (
                    action_id, session_id, stage_id, node_id, source_type, source_id,
                    action_type, status, risk_level, title, description, trigger_reason,
                    blocking, payload_before, payload_after, reviewer_decision,
                    reviewer_note, stage_output_version, superseded_by,
                    action_contract_id, action_schema_version, idempotency_key,
                    target_stage, target_stage_version, target_object_path,
                    expected_before_hash, approved_payload_hash, resume_token, expires_at,
                    resolution_attempts, last_resolution_error, created_at, resolved_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                ON CONFLICT (action_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    payload_after = EXCLUDED.payload_after,
                    reviewer_decision = EXCLUDED.reviewer_decision,
                    reviewer_note = EXCLUDED.reviewer_note,
                    stage_output_version = EXCLUDED.stage_output_version,
                    superseded_by = EXCLUDED.superseded_by,
                    idempotency_key = EXCLUDED.idempotency_key,
                    target_stage = EXCLUDED.target_stage,
                    target_stage_version = EXCLUDED.target_stage_version,
                    target_object_path = EXCLUDED.target_object_path,
                    expected_before_hash = EXCLUDED.expected_before_hash,
                    approved_payload_hash = EXCLUDED.approved_payload_hash,
                    resume_token = EXCLUDED.resume_token,
                    expires_at = EXCLUDED.expires_at,
                    resolution_attempts = EXCLUDED.resolution_attempts,
                    last_resolution_error = EXCLUDED.last_resolution_error,
                    resolved_at = EXCLUDED.resolved_at
                """,
                (
                    action.action_id,
                    ctx.session_id,
                    action.stage_id,
                    action.node_id,
                    action.source_type,
                    action.source_id,
                    action.action_type,
                    action.status,
                    action.risk_level,
                    action.title,
                    action.description,
                    action.trigger_reason,
                    action.blocking,
                    json.dumps(action.payload_before, default=str),
                    json.dumps(action.payload_after, default=str)
                    if action.payload_after is not None
                    else None,
                    action.reviewer_decision,
                    action.reviewer_note,
                    action.stage_output_version,
                    action.superseded_by,
                    action.action_contract_id,
                    action.action_schema_version,
                    action.idempotency_key,
                    action.target_stage,
                    action.target_stage_version,
                    action.target_object_path,
                    action.expected_before_hash,
                    action.approved_payload_hash,
                    action.resume_token,
                    action.expires_at,
                    action.resolution_attempts,
                    action.last_resolution_error,
                    action.created_at,
                    action.resolved_at,
                ),
            )

    def _sync_action_resolution_logs(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        """同步 action resolution logs。append-only：已存在 log_id 不覆盖。"""
        for log in getattr(ctx, "action_resolution_logs", []) or []:
            conn.execute(
                """
                INSERT INTO action_resolution_logs (
                    log_id, session_id, action_id, idempotency_key, requested_status,
                    result_status, before_hash, after_hash, error_message, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (log_id) DO NOTHING
                """,
                (
                    log.log_id,
                    ctx.session_id,
                    log.action_id,
                    log.idempotency_key,
                    log.requested_status,
                    log.result_status,
                    log.before_hash,
                    log.after_hash,
                    log.error_message,
                    log.created_at,
                ),
            )

    def _sync_llm_traces(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        """同步 LLM traces。append-only：已存在 trace_id 不覆盖。"""
        for trace in getattr(ctx, "llm_traces", []) or []:
            conn.execute(
                """
                INSERT INTO llm_traces (
                    trace_id, session_id, stage, node_name, trace_type, provider, model,
                    prompt_template_id, prompt_template_version, input_token_count,
                    output_token_count, estimated_cost, latency_ms, retry_count,
                    parser_status, safety_status, evidence_count, error_type,
                    error_message, metadata, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (trace_id) DO NOTHING
                """,
                (
                    trace.trace_id,
                    ctx.session_id,
                    trace.stage,
                    trace.node_name,
                    trace.trace_type,
                    trace.provider,
                    trace.model,
                    trace.prompt_template_id,
                    trace.prompt_template_version,
                    trace.input_token_count,
                    trace.output_token_count,
                    trace.estimated_cost,
                    trace.latency_ms,
                    trace.retry_count,
                    trace.parser_status,
                    trace.safety_status,
                    trace.evidence_count,
                    trace.error_type,
                    trace.error_message,
                    json.dumps(trace.metadata, default=str),
                    trace.created_at,
                ),
            )

    @staticmethod
    def _truncate_snapshot(snapshot: dict | None, max_bytes: int = 50_000) -> dict | None:
        """Truncate a snapshot dict if its JSON representation exceeds max_bytes.

        Individual snapshots can contain full stage outputs (100KB+ each).
        With many audit events, total can exceed PostgreSQL JSONB limits.
        Truncate aggressively — full snapshots are not needed for audit indexing.
        """
        if snapshot is None:
            return None
        raw = json.dumps(snapshot, default=str)
        if len(raw.encode("utf-8")) <= max_bytes:
            return snapshot
        # Return a truncated version with a marker
        truncated = {}
        for key, value in snapshot.items():
            val_str = json.dumps(value, default=str)
            if len(val_str.encode("utf-8")) > 5_000:
                truncated[key] = f"<truncated: {len(val_str)} bytes>"
            else:
                truncated[key] = value
        truncated["_truncated"] = True
        truncated["_original_size_bytes"] = len(raw.encode("utf-8"))
        return truncated

    def _sync_audit_events(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        """同步审计事件。append-only：已存在 event_id 不覆盖、不删除。"""
        for event in ctx.audit_events:
            conn.execute(
                """
                INSERT INTO audit_events (
                    event_id, session_id, actor, event_type, target_type, target_id,
                    before_hash, after_hash, before_snapshot, after_snapshot, metadata, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (event_id) DO NOTHING
                """,
                (
                    event.event_id,
                    ctx.session_id,
                    event.actor,
                    event.event_type,
                    event.target_type,
                    event.target_id,
                    event.before_hash,
                    event.after_hash,
                    json.dumps(self._truncate_snapshot(event.before_snapshot), default=str)
                    if event.before_snapshot is not None
                    else None,
                    json.dumps(self._truncate_snapshot(event.after_snapshot), default=str)
                    if event.after_snapshot is not None
                    else None,
                    json.dumps(event.metadata, default=str),
                    event.created_at,
                ),
            )

    def _sync_evidence_sources(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        for ev in ctx.evidence_sources:
            conn.execute(
                """
                INSERT INTO evidence_sources (
                    evidence_id, session_id, title, url, source_type, credibility_score,
                    summary, claims, used_by_failure_mode_ids, verified, verified_by,
                    verified_at, verification_note, retrieved_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (evidence_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    url = EXCLUDED.url,
                    source_type = EXCLUDED.source_type,
                    credibility_score = EXCLUDED.credibility_score,
                    summary = EXCLUDED.summary,
                    claims = EXCLUDED.claims,
                    used_by_failure_mode_ids = EXCLUDED.used_by_failure_mode_ids,
                    verified = EXCLUDED.verified,
                    verified_by = EXCLUDED.verified_by,
                    verified_at = EXCLUDED.verified_at,
                    verification_note = EXCLUDED.verification_note
                """,
                (
                    ev.evidence_id,
                    ctx.session_id,
                    ev.title,
                    ev.url,
                    ev.source_type,
                    ev.credibility_score,
                    ev.summary,
                    json.dumps(ev.claims, default=str),
                    json.dumps(ev.used_by_failure_mode_ids, default=str),
                    ev.verified,
                    ev.verified_by,
                    ev.verified_at,
                    ev.verification_note,
                    ev.retrieved_at,
                ),
            )

    def _sync_safety_findings(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        for finding in ctx.safety_findings:
            conn.execute(
                """
                INSERT INTO safety_findings (
                    finding_id, session_id, stage_id, risk_type, severity, location,
                    description, recommended_action, requires_human_review, status,
                    taxonomy_refs, control_refs, mitigation_status, residual_risk,
                    resolution_note, resolved_at, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (finding_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    recommended_action = EXCLUDED.recommended_action,
                    requires_human_review = EXCLUDED.requires_human_review,
                    taxonomy_refs = EXCLUDED.taxonomy_refs,
                    control_refs = EXCLUDED.control_refs,
                    mitigation_status = EXCLUDED.mitigation_status,
                    residual_risk = EXCLUDED.residual_risk,
                    resolution_note = EXCLUDED.resolution_note,
                    resolved_at = EXCLUDED.resolved_at
                """,
                (
                    finding.finding_id,
                    ctx.session_id,
                    finding.stage_id,
                    finding.risk_type,
                    finding.severity,
                    finding.location,
                    finding.description,
                    finding.recommended_action,
                    finding.requires_human_review,
                    finding.status,
                    json.dumps(getattr(finding, "taxonomy_refs", []), default=str),
                    json.dumps(getattr(finding, "control_refs", []), default=str),
                    getattr(finding, "mitigation_status", "open"),
                    getattr(finding, "residual_risk", "unknown"),
                    finding.resolution_note,
                    finding.resolved_at,
                    finding.created_at,
                ),
            )

    @staticmethod
    def _truncate_report_content_json(content_json: dict) -> dict:
        """Truncate large fields in report content_json for DB storage.

        Full audit events are in audit_events table; report only needs summaries.
        """
        truncated = dict(content_json)
        # Truncate audit events — remove large snapshots
        if "audit_events" in truncated:
            truncated["audit_events"] = [
                {
                    "event_id": ev.get("event_id"),
                    "actor": ev.get("actor"),
                    "event_type": ev.get("event_type"),
                    "target_type": ev.get("target_type"),
                    "target_id": ev.get("target_id"),
                    "created_at": ev.get("created_at"),
                }
                for ev in truncated["audit_events"]
            ]
        return truncated

    def _sync_report_artifacts(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        for artifact in ctx.report_artifacts:
            truncated_content = self._truncate_report_content_json(artifact.content_json)
            conn.execute(
                """
                INSERT INTO report_artifacts (
                    report_id, session_id, version, content_json, content_markdown, generated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (report_id) DO UPDATE SET
                    version = EXCLUDED.version,
                    content_json = EXCLUDED.content_json,
                    content_markdown = EXCLUDED.content_markdown
                """,
                (
                    artifact.report_id,
                    ctx.session_id,
                    artifact.version,
                    json.dumps(truncated_content, default=str),
                    artifact.content_markdown,
                    artifact.generated_at,
                ),
            )

    def _sync_eval_cases(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        for case in ctx.eval_cases:
            conn.execute(
                """
                INSERT INTO eval_cases (
                    eval_id, session_id, stage_id, target_node_id, covered_failure_mode_ids,
                    scenario_type, source_type, source_trace_id, source_ref_id, metadata,
                    input_payload, expected_behavior, pass_criteria, actual_output, human_score,
                    human_comment, passed, created_at, scored_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (eval_id) DO UPDATE SET
                    covered_failure_mode_ids = EXCLUDED.covered_failure_mode_ids,
                    source_type = EXCLUDED.source_type,
                    source_trace_id = EXCLUDED.source_trace_id,
                    source_ref_id = EXCLUDED.source_ref_id,
                    metadata = EXCLUDED.metadata,
                    pass_criteria = EXCLUDED.pass_criteria,
                    actual_output = EXCLUDED.actual_output,
                    human_score = EXCLUDED.human_score,
                    human_comment = EXCLUDED.human_comment,
                    passed = EXCLUDED.passed,
                    scored_at = EXCLUDED.scored_at
                """,
                (
                    case.eval_id,
                    ctx.session_id,
                    case.stage_id,
                    case.target_node_id,
                    json.dumps(case.covered_failure_mode_ids, default=str),
                    case.scenario_type,
                    getattr(case, "source_type", "stage3_generated"),
                    getattr(case, "source_trace_id", None),
                    getattr(case, "source_ref_id", None),
                    json.dumps(getattr(case, "metadata", {}), default=str),
                    case.input_payload,
                    case.expected_behavior,
                    json.dumps(case.pass_criteria, default=str),
                    case.actual_output,
                    case.human_score,
                    case.human_comment,
                    case.passed,
                    case.created_at,
                    case.scored_at,
                ),
            )

    def _sync_eval_runs(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        for run in ctx.eval_runs:
            conn.execute(
                """
                INSERT INTO eval_runs (
                    run_id, session_id, eval_id, dataset_id, experiment_id, run_index,
                    target_node_id, covered_failure_mode_ids,
                    stage_output_version, run_mode, input_payload, expected_behavior,
                    actual_output, judge_result, judge_reason, judge_mode, violated_criteria,
                    status, error_message, trace_id, latency_ms, estimated_cost, created_at, completed_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id) DO UPDATE SET
                    dataset_id = EXCLUDED.dataset_id,
                    experiment_id = EXCLUDED.experiment_id,
                    run_index = EXCLUDED.run_index,
                    actual_output = EXCLUDED.actual_output,
                    judge_result = EXCLUDED.judge_result,
                    judge_reason = EXCLUDED.judge_reason,
                    judge_mode = EXCLUDED.judge_mode,
                    violated_criteria = EXCLUDED.violated_criteria,
                    status = EXCLUDED.status,
                    error_message = EXCLUDED.error_message,
                    trace_id = EXCLUDED.trace_id,
                    latency_ms = EXCLUDED.latency_ms,
                    estimated_cost = EXCLUDED.estimated_cost,
                    completed_at = EXCLUDED.completed_at
                """,
                (
                    run.run_id,
                    ctx.session_id,
                    run.eval_id,
                    run.dataset_id,
                    run.experiment_id,
                    run.run_index,
                    run.target_node_id,
                    json.dumps(run.covered_failure_mode_ids, default=str),
                    run.stage_output_version,
                    run.run_mode,
                    run.input_payload,
                    run.expected_behavior,
                    run.actual_output,
                    run.judge_result,
                    run.judge_reason,
                    run.judge_mode,
                    json.dumps(run.violated_criteria, default=str),
                    run.status,
                    run.error_message,
                    run.trace_id,
                    run.latency_ms,
                    run.estimated_cost,
                    run.created_at,
                    run.completed_at,
                ),
            )

    def _sync_eval_judgments(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        for judgment in getattr(ctx, "eval_judgments", []) or []:
            conn.execute(
                """
                INSERT INTO eval_judgments (
                    judgment_id, session_id, eval_run_id, eval_id, experiment_id, judge_type,
                    judge_model, score, label, rationale, uncertainty, cited_rules, payload_json, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (judgment_id) DO UPDATE SET
                    label = EXCLUDED.label,
                    rationale = EXCLUDED.rationale,
                    uncertainty = EXCLUDED.uncertainty,
                    cited_rules = EXCLUDED.cited_rules,
                    payload_json = EXCLUDED.payload_json
                """,
                (
                    judgment.judgment_id,
                    ctx.session_id,
                    judgment.eval_run_id,
                    judgment.eval_id,
                    judgment.experiment_id,
                    judgment.judge_type,
                    judgment.judge_model,
                    judgment.score,
                    judgment.label,
                    judgment.rationale,
                    judgment.uncertainty,
                    json.dumps(judgment.cited_rules, default=str),
                    json.dumps(judgment.model_dump(mode="json"), default=str),
                    judgment.created_at,
                ),
            )

    def _sync_human_calibrations(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        for calibration in getattr(ctx, "human_calibrations", []) or []:
            conn.execute(
                """
                INSERT INTO human_calibrations (
                    calibration_id, session_id, eval_run_id, eval_id, experiment_id, human_label,
                    human_comment, judge_label, agreement, disagreement_reason, reviewer_id,
                    payload_json, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (calibration_id) DO UPDATE SET
                    human_label = EXCLUDED.human_label,
                    human_comment = EXCLUDED.human_comment,
                    judge_label = EXCLUDED.judge_label,
                    agreement = EXCLUDED.agreement,
                    disagreement_reason = EXCLUDED.disagreement_reason,
                    reviewer_id = EXCLUDED.reviewer_id,
                    payload_json = EXCLUDED.payload_json
                """,
                (
                    calibration.calibration_id,
                    ctx.session_id,
                    calibration.eval_run_id,
                    calibration.eval_id,
                    calibration.experiment_id,
                    calibration.human_label,
                    calibration.human_comment,
                    calibration.judge_label,
                    calibration.agreement,
                    calibration.disagreement_reason,
                    calibration.reviewer_id,
                    json.dumps(calibration.model_dump(mode="json"), default=str),
                    calibration.created_at,
                ),
            )

    def _sync_eval_datasets(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        for dataset in getattr(ctx, "eval_datasets", []) or []:
            conn.execute(
                """
                INSERT INTO eval_datasets (
                    dataset_id, session_id, name, version, source, stage, scenario_type,
                    case_ids, payload_json, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (dataset_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    version = EXCLUDED.version,
                    source = EXCLUDED.source,
                    stage = EXCLUDED.stage,
                    scenario_type = EXCLUDED.scenario_type,
                    case_ids = EXCLUDED.case_ids,
                    payload_json = EXCLUDED.payload_json,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    dataset.dataset_id,
                    ctx.session_id,
                    dataset.name,
                    dataset.version,
                    dataset.source,
                    dataset.stage,
                    dataset.scenario_type,
                    json.dumps(dataset.case_ids, default=str),
                    json.dumps(dataset.model_dump(mode="json"), default=str),
                    dataset.created_at,
                    dataset.updated_at,
                ),
            )

    def _sync_eval_experiments(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        for experiment in getattr(ctx, "eval_experiments", []) or []:
            conn.execute(
                """
                INSERT INTO eval_experiments (
                    experiment_id, session_id, dataset_id, name, status, run_mode, provider,
                    model, baseline_experiment_id, eval_ids, run_ids, aggregate_metrics,
                    comparison_summary, payload_json, created_at, started_at, completed_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (experiment_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    status = EXCLUDED.status,
                    run_mode = EXCLUDED.run_mode,
                    provider = EXCLUDED.provider,
                    model = EXCLUDED.model,
                    baseline_experiment_id = EXCLUDED.baseline_experiment_id,
                    eval_ids = EXCLUDED.eval_ids,
                    run_ids = EXCLUDED.run_ids,
                    aggregate_metrics = EXCLUDED.aggregate_metrics,
                    comparison_summary = EXCLUDED.comparison_summary,
                    payload_json = EXCLUDED.payload_json,
                    started_at = EXCLUDED.started_at,
                    completed_at = EXCLUDED.completed_at
                """,
                (
                    experiment.experiment_id,
                    ctx.session_id,
                    experiment.dataset_id,
                    experiment.name,
                    experiment.status,
                    experiment.run_mode,
                    experiment.provider,
                    experiment.model,
                    experiment.baseline_experiment_id,
                    json.dumps(experiment.eval_ids, default=str),
                    json.dumps(experiment.run_ids, default=str),
                    json.dumps(experiment.aggregate_metrics.model_dump(mode="json"), default=str),
                    json.dumps(experiment.comparison_summary, default=str),
                    json.dumps(experiment.model_dump(mode="json"), default=str),
                    experiment.created_at,
                    experiment.started_at,
                    experiment.completed_at,
                ),
            )

    def _sync_redteam_cases(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        for case in getattr(ctx, "redteam_cases", []) or []:
            conn.execute(
                """
                INSERT INTO redteam_cases (
                    redteam_case_id, session_id, target_stage, target_node_id,
                    source_finding_id, source_failure_mode_id, attack_type, severity,
                    status, linked_eval_case_id, taxonomy_refs, control_refs,
                    payload_json, created_at, approved_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (redteam_case_id) DO UPDATE SET
                    target_stage = EXCLUDED.target_stage,
                    target_node_id = EXCLUDED.target_node_id,
                    source_finding_id = EXCLUDED.source_finding_id,
                    source_failure_mode_id = EXCLUDED.source_failure_mode_id,
                    attack_type = EXCLUDED.attack_type,
                    severity = EXCLUDED.severity,
                    status = EXCLUDED.status,
                    linked_eval_case_id = EXCLUDED.linked_eval_case_id,
                    taxonomy_refs = EXCLUDED.taxonomy_refs,
                    control_refs = EXCLUDED.control_refs,
                    payload_json = EXCLUDED.payload_json,
                    approved_at = EXCLUDED.approved_at,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    case.redteam_case_id,
                    ctx.session_id,
                    case.target_stage,
                    case.target_node_id,
                    case.source_finding_id,
                    case.source_failure_mode_id,
                    case.attack_type,
                    case.severity,
                    case.status,
                    case.linked_eval_case_id,
                    json.dumps(getattr(case, "taxonomy_refs", []), default=str),
                    json.dumps(getattr(case, "control_refs", []), default=str),
                    json.dumps(case.model_dump(mode="json"), default=str),
                    case.created_at,
                    case.approved_at,
                    case.updated_at,
                ),
            )

    def _sync_interrupt_records(self, conn: psycopg.Connection, ctx: ProjectContext) -> None:
        """同步业务中断记录，为 v0.6 interrupt/checkpoint adapter 做持久化准备。"""
        for record in getattr(ctx, "interrupt_records", []) or []:
            conn.execute(
                """
                INSERT INTO interrupt_records (
                    interrupt_id, session_id, action_id, stage_id, stage_output_version,
                    status, resume_value, thread_id, node_name, checkpoint_ns,
                    interrupt_payload, resume_consumed_at, created_at, resolved_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (interrupt_id) DO UPDATE SET
                    action_id = EXCLUDED.action_id,
                    stage_id = EXCLUDED.stage_id,
                    stage_output_version = EXCLUDED.stage_output_version,
                    status = EXCLUDED.status,
                    resume_value = EXCLUDED.resume_value,
                    thread_id = EXCLUDED.thread_id,
                    node_name = EXCLUDED.node_name,
                    checkpoint_ns = EXCLUDED.checkpoint_ns,
                    interrupt_payload = EXCLUDED.interrupt_payload,
                    resume_consumed_at = EXCLUDED.resume_consumed_at,
                    resolved_at = EXCLUDED.resolved_at
                """,
                (
                    record.interrupt_id,
                    ctx.session_id,
                    record.action_id,
                    record.stage_id,
                    record.stage_output_version,
                    record.status,
                    json.dumps(record.resume_value, default=str)
                    if record.resume_value is not None
                    else None,
                    record.thread_id,
                    record.node_name,
                    record.checkpoint_ns,
                    json.dumps(record.interrupt_payload, default=str)
                    if record.interrupt_payload is not None
                    else None,
                    record.resume_consumed_at,
                    record.created_at,
                    record.resolved_at,
                ),
            )

    def list_interrupt_records(self, session_id: str) -> list[dict]:
        """从独立 interrupt_records 表读取执行中断记录。"""
        sql = """
            SELECT interrupt_id, session_id, action_id, stage_id, stage_output_version,
                   status, resume_value, thread_id, node_name, checkpoint_ns,
                   interrupt_payload, resume_consumed_at, created_at, resolved_at
            FROM interrupt_records
            WHERE session_id = %s
            ORDER BY created_at DESC
        """
        with self._get_conn() as conn:
            rows = conn.execute(sql, (session_id,)).fetchall()
        return [self._interrupt_row_to_dict(row) for row in rows]

    def get_interrupt_record(self, session_id: str, interrupt_id: str) -> dict | None:
        """读取单条执行中断记录。"""
        sql = """
            SELECT interrupt_id, session_id, action_id, stage_id, stage_output_version,
                   status, resume_value, thread_id, node_name, checkpoint_ns,
                   interrupt_payload, resume_consumed_at, created_at, resolved_at
            FROM interrupt_records
            WHERE session_id = %s AND interrupt_id = %s
        """
        with self._get_conn() as conn:
            row = conn.execute(sql, (session_id, interrupt_id)).fetchone()
        if not row:
            return None
        return self._interrupt_row_to_dict(row)

    @staticmethod
    def _interrupt_row_to_dict(row: dict) -> dict:
        item = dict(row)
        for key in ("created_at", "resolved_at", "resume_consumed_at"):
            if item.get(key) and hasattr(item[key], "isoformat"):
                item[key] = item[key].isoformat()
        return item

    def list_report_artifacts(self, session_id: str) -> list[dict]:
        """从独立 report_artifacts 表读取报告快照列表。"""
        sql = """
            SELECT report_id, session_id, version, content_json, content_markdown, generated_at
            FROM report_artifacts
            WHERE session_id = %s
            ORDER BY generated_at DESC
        """
        with self._get_conn() as conn:
            rows = conn.execute(sql, (session_id,)).fetchall()
        artifacts: list[dict] = []
        for row in rows:
            content = row.get("content_json") or {}
            artifacts.append(
                {
                    "report_id": row["report_id"],
                    "session_id": row["session_id"],
                    "version": row["version"],
                    "generated_at": row["generated_at"].isoformat()
                    if row.get("generated_at")
                    else None,
                    "content_json": content,
                    "content_markdown": row.get("content_markdown") or "",
                    "ai_generated": content.get("ai_generated", {}),
                    "human_reviewed": content.get("human_reviewed", {}),
                    "evidence": content.get("evidence_sources", []),
                    "audit_events": content.get("audit_events", []),
                    "open_risks": content.get("open_risks", []),
                    "eval_summary": content.get("eval_summary", {}),
                    "eval_runs": content.get("eval_runs", []),
                    "failed_eval_runs": content.get("failed_eval_runs", []),
                }
            )
        return artifacts

    def get_report_artifact(self, session_id: str, report_id: str) -> dict | None:
        """从独立 report_artifacts 表读取单个报告快照。"""
        sql = """
            SELECT report_id, session_id, version, content_json, content_markdown, generated_at
            FROM report_artifacts
            WHERE session_id = %s AND report_id = %s
        """
        with self._get_conn() as conn:
            row = conn.execute(sql, (session_id, report_id)).fetchone()
        if not row:
            return None
        content = row.get("content_json") or {}
        return {
            "report_id": row["report_id"],
            "session_id": row["session_id"],
            "version": row["version"],
            "generated_at": row["generated_at"].isoformat() if row.get("generated_at") else None,
            "content_json": content,
            "content_markdown": row.get("content_markdown") or "",
            "ai_generated": content.get("ai_generated", {}),
            "human_reviewed": content.get("human_reviewed", {}),
            "evidence": content.get("evidence_sources", []),
            "audit_events": content.get("audit_events", []),
            "open_risks": content.get("open_risks", []),
            "eval_summary": content.get("eval_summary", {}),
            "eval_runs": content.get("eval_runs", []),
            "failed_eval_runs": content.get("failed_eval_runs", []),
        }

    def load(self, session_id: str) -> ProjectContext | None:
        """加载会话，不存在则返回 None"""
        sql = "SELECT context_json FROM sessions WHERE session_id = %s"
        with self._get_conn() as conn:
            row = conn.execute(sql, (session_id,)).fetchone()
        if not row:
            return None
        return migrate_context(row["context_json"])

    def list_sessions(self, limit: int = 20) -> list[dict]:
        """列出最近的会话（用于前端历史列表）"""
        sql = """
            SELECT session_id, current_state, created_at, updated_at,
                   context_json->>'research_target' AS research_target,
                   context_json->>'domain' AS domain
            FROM sessions
            ORDER BY updated_at DESC
            LIMIT %s
        """
        with self._get_conn() as conn:
            rows = conn.execute(sql, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def log_event(
        self,
        session_id: str,
        event_type: str,
        stage: int | None,
        payload: dict,
    ) -> None:
        """记录会话事件（用于审计和调试）"""
        sql = """
            INSERT INTO session_events (session_id, event_type, stage, payload)
            VALUES (%s, %s, %s, %s)
        """
        with self._get_conn() as conn:
            conn.execute(sql, (session_id, event_type, stage, json.dumps(payload, default=str)))
            conn.commit()


# 全局单例
session_store = SessionStore()
