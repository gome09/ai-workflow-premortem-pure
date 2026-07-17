# storage/backends/sqlite_store.py
"""SQLite session-store backend — stdlib only, no external services required."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from core.migrations import migrate_context
from core.models import ProjectContext
from storage.field_security import decrypt_fields_after_load, encrypt_fields_for_storage

logger = logging.getLogger(__name__)

# Default DB path; can be overridden via SQLITE_PATH env var.
_DEFAULT_DB_PATH = "data/workflow.db"

_INIT_DDL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id    TEXT PRIMARY KEY,
    current_state TEXT NOT NULL DEFAULT 'init',
    context_json  TEXT NOT NULL DEFAULT '{}',
    tenant_id     TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_state   ON sessions (current_state);
CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_tenant  ON sessions (tenant_id);

CREATE TABLE IF NOT EXISTS session_events (
    event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    stage      INTEGER,
    payload    TEXT NOT NULL DEFAULT '{}',
    tenant_id  TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_events_session ON session_events (session_id, created_at DESC);

CREATE TABLE IF NOT EXISTS human_actions (
    action_id             TEXT PRIMARY KEY,
    session_id            TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    stage_id              INTEGER NOT NULL,
    node_id               TEXT,
    source_type           TEXT,
    source_id             TEXT,
    action_type           TEXT NOT NULL,
    status                TEXT NOT NULL DEFAULT 'pending',
    risk_level            TEXT NOT NULL DEFAULT 'medium',
    title                 TEXT NOT NULL,
    description           TEXT NOT NULL,
    trigger_reason        TEXT,
    blocking              INTEGER NOT NULL DEFAULT 1,
    payload_before        TEXT NOT NULL DEFAULT '{}',
    payload_after         TEXT,
    reviewer_decision     TEXT,
    reviewer_note         TEXT,
    stage_output_version  INTEGER NOT NULL DEFAULT 1,
    superseded_by         TEXT,
    action_contract_id    TEXT,
    action_schema_version TEXT,
    idempotency_key       TEXT,
    target_stage          INTEGER,
    target_stage_version  INTEGER,
    target_object_path    TEXT,
    expected_before_hash  TEXT,
    approved_payload_hash TEXT,
    resume_token          TEXT,
    expires_at            TEXT,
    resolution_attempts   INTEGER,
    last_resolution_error TEXT,
    created_at            TEXT NOT NULL,
    resolved_at           TEXT
);
CREATE INDEX IF NOT EXISTS idx_human_actions_session ON human_actions (session_id, status, stage_id);

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
    created_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_action_resolution_logs_session ON action_resolution_logs (session_id, action_id);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id        TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    actor           TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    target_type     TEXT NOT NULL,
    target_id       TEXT NOT NULL,
    before_hash     TEXT,
    after_hash      TEXT,
    before_snapshot TEXT,
    after_snapshot  TEXT,
    metadata        TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_events_session ON audit_events (session_id, created_at DESC);

CREATE TABLE IF NOT EXISTS audit_events_archive (
    archive_id           TEXT PRIMARY KEY,
    original_session_id  TEXT NOT NULL,
    event_id             TEXT NOT NULL,
    actor                TEXT NOT NULL,
    event_type           TEXT NOT NULL,
    target_type          TEXT NOT NULL,
    target_id            TEXT NOT NULL,
    before_hash          TEXT,
    after_hash           TEXT,
    before_snapshot      TEXT,
    after_snapshot       TEXT,
    metadata             TEXT NOT NULL DEFAULT '{}',
    original_created_at  TEXT NOT NULL,
    archived_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_archive_session ON audit_events_archive (original_session_id, original_created_at DESC);

CREATE TABLE IF NOT EXISTS evidence_sources (
    evidence_id              TEXT PRIMARY KEY,
    session_id               TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    title                    TEXT NOT NULL,
    url                      TEXT,
    source_type              TEXT NOT NULL,
    credibility_score        REAL NOT NULL DEFAULT 0,
    summary                  TEXT,
    claims                   TEXT NOT NULL DEFAULT '[]',
    used_by_failure_mode_ids TEXT NOT NULL DEFAULT '[]',
    verified                 INTEGER NOT NULL DEFAULT 0,
    verified_by              TEXT,
    verified_at              TEXT,
    verification_note        TEXT,
    retrieved_at             TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evidence_sources_session ON evidence_sources (session_id);

CREATE TABLE IF NOT EXISTS safety_findings (
    finding_id            TEXT PRIMARY KEY,
    session_id            TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    stage_id              INTEGER,
    risk_type             TEXT NOT NULL,
    severity              TEXT NOT NULL,
    location              TEXT NOT NULL,
    description           TEXT NOT NULL,
    recommended_action    TEXT NOT NULL,
    requires_human_review INTEGER NOT NULL DEFAULT 0,
    status                TEXT NOT NULL DEFAULT 'open',
    taxonomy_refs         TEXT NOT NULL DEFAULT '[]',
    control_refs          TEXT NOT NULL DEFAULT '[]',
    mitigation_status     TEXT NOT NULL DEFAULT 'open',
    residual_risk         TEXT NOT NULL DEFAULT 'unknown',
    resolution_note       TEXT NOT NULL DEFAULT '',
    resolved_at           TEXT,
    created_at            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_safety_findings_session ON safety_findings (session_id, status);

CREATE TABLE IF NOT EXISTS report_artifacts (
    report_id        TEXT PRIMARY KEY,
    session_id       TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    version          TEXT NOT NULL,
    content_json     TEXT NOT NULL DEFAULT '{}',
    content_markdown TEXT NOT NULL DEFAULT '',
    generated_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_report_artifacts_session ON report_artifacts (session_id, generated_at DESC);

CREATE TABLE IF NOT EXISTS eval_cases (
    eval_id                  TEXT PRIMARY KEY,
    session_id               TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    stage_id                 INTEGER NOT NULL DEFAULT 3,
    target_node_id           TEXT,
    covered_failure_mode_ids TEXT NOT NULL DEFAULT '[]',
    scenario_type            TEXT NOT NULL,
    source_type              TEXT NOT NULL DEFAULT 'stage3_generated',
    source_trace_id          TEXT,
    source_ref_id            TEXT,
    metadata                 TEXT NOT NULL DEFAULT '{}',
    input_payload            TEXT NOT NULL,
    expected_behavior        TEXT NOT NULL,
    pass_criteria            TEXT NOT NULL DEFAULT '[]',
    actual_output            TEXT,
    human_score              INTEGER,
    human_comment            TEXT,
    passed                   INTEGER,
    created_at               TEXT NOT NULL,
    scored_at                TEXT
);
CREATE INDEX IF NOT EXISTS idx_eval_cases_session ON eval_cases (session_id, stage_id);

CREATE TABLE IF NOT EXISTS eval_runs (
    run_id                   TEXT PRIMARY KEY,
    session_id               TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    eval_id                  TEXT NOT NULL,
    dataset_id               TEXT,
    experiment_id            TEXT,
    run_index                INTEGER,
    target_node_id           TEXT,
    covered_failure_mode_ids TEXT NOT NULL DEFAULT '[]',
    stage_output_version     INTEGER NOT NULL DEFAULT 1,
    run_mode                 TEXT NOT NULL,
    input_payload            TEXT NOT NULL,
    expected_behavior        TEXT NOT NULL,
    actual_output            TEXT,
    judge_result             TEXT,
    judge_reason             TEXT NOT NULL DEFAULT '',
    judge_mode               TEXT NOT NULL DEFAULT 'inherited',
    violated_criteria        TEXT NOT NULL DEFAULT '[]',
    status                   TEXT NOT NULL DEFAULT 'created',
    error_message            TEXT NOT NULL DEFAULT '',
    trace_id                 TEXT,
    latency_ms               INTEGER,
    estimated_cost           REAL,
    created_at               TEXT NOT NULL,
    completed_at             TEXT
);
CREATE INDEX IF NOT EXISTS idx_eval_runs_session ON eval_runs (session_id, eval_id);

CREATE TABLE IF NOT EXISTS eval_judgments (
    judgment_id  TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    eval_run_id  TEXT,
    eval_id      TEXT,
    experiment_id TEXT,
    judge_type   TEXT,
    judge_model  TEXT,
    score        REAL,
    label        TEXT,
    rationale    TEXT,
    uncertainty  REAL,
    cited_rules  TEXT NOT NULL DEFAULT '[]',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_eval_judgments_session ON eval_judgments (session_id);

CREATE TABLE IF NOT EXISTS human_calibrations (
    calibration_id     TEXT PRIMARY KEY,
    session_id         TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    eval_run_id        TEXT,
    eval_id            TEXT,
    experiment_id      TEXT,
    human_label        TEXT,
    human_comment      TEXT,
    judge_label        TEXT,
    agreement          INTEGER,
    disagreement_reason TEXT,
    reviewer_id        TEXT,
    payload_json       TEXT NOT NULL DEFAULT '{}',
    created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_human_calibrations_session ON human_calibrations (session_id);

CREATE TABLE IF NOT EXISTS eval_datasets (
    dataset_id    TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    version       TEXT NOT NULL,
    source        TEXT,
    stage         INTEGER,
    scenario_type TEXT,
    case_ids      TEXT NOT NULL DEFAULT '[]',
    payload_json  TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT,
    updated_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_eval_datasets_session ON eval_datasets (session_id);

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
    eval_ids               TEXT NOT NULL DEFAULT '[]',
    run_ids                TEXT NOT NULL DEFAULT '[]',
    aggregate_metrics      TEXT NOT NULL DEFAULT '{}',
    comparison_summary     TEXT NOT NULL DEFAULT '{}',
    payload_json           TEXT NOT NULL DEFAULT '{}',
    created_at             TEXT,
    started_at             TEXT,
    completed_at           TEXT
);
CREATE INDEX IF NOT EXISTS idx_eval_experiments_session ON eval_experiments (session_id);

CREATE TABLE IF NOT EXISTS redteam_cases (
    redteam_case_id       TEXT PRIMARY KEY,
    session_id            TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    target_stage          INTEGER NOT NULL DEFAULT 3,
    target_node_id        TEXT,
    source_finding_id     TEXT,
    source_failure_mode_id TEXT,
    attack_type           TEXT,
    severity              TEXT,
    status                TEXT,
    linked_eval_case_id   TEXT,
    taxonomy_refs         TEXT NOT NULL DEFAULT '[]',
    control_refs          TEXT NOT NULL DEFAULT '[]',
    payload_json          TEXT NOT NULL DEFAULT '{}',
    created_at            TEXT NOT NULL,
    approved_at           TEXT,
    updated_at            TEXT
);
CREATE INDEX IF NOT EXISTS idx_redteam_cases_session ON redteam_cases (session_id);

CREATE TABLE IF NOT EXISTS llm_traces (
    trace_id               TEXT PRIMARY KEY,
    session_id             TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    stage                  INTEGER,
    node_name              TEXT,
    trace_type             TEXT,
    provider               TEXT,
    model                  TEXT,
    prompt_template_id     TEXT,
    prompt_template_version TEXT,
    input_token_count      INTEGER,
    output_token_count     INTEGER,
    estimated_cost         REAL,
    latency_ms             INTEGER,
    retry_count            INTEGER,
    parser_status          TEXT,
    safety_status          TEXT,
    evidence_count         INTEGER,
    error_type             TEXT,
    error_message          TEXT,
    metadata               TEXT NOT NULL DEFAULT '{}',
    created_at             TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_llm_traces_session ON llm_traces (session_id, stage);

CREATE TABLE IF NOT EXISTS interrupt_records (
    interrupt_id          TEXT PRIMARY KEY,
    session_id            TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    action_id             TEXT,
    stage_id              TEXT,
    stage_output_version  INTEGER,
    status                TEXT,
    resume_value          TEXT,
    thread_id             TEXT,
    node_name             TEXT,
    checkpoint_ns         TEXT,
    interrupt_payload     TEXT,
    resume_consumed_at    TEXT,
    created_at            TEXT NOT NULL,
    resolved_at           TEXT
);
CREATE INDEX IF NOT EXISTS idx_interrupt_records_session ON interrupt_records (session_id);

CREATE TABLE IF NOT EXISTS tenants (
    tenant_id  TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS users (
    user_id       TEXT PRIMARY KEY,
    tenant_id     TEXT NOT NULL REFERENCES tenants(tenant_id),
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'viewer',
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS gate_evaluation_records (
    record_id           TEXT PRIMARY KEY,
    session_id          TEXT NOT NULL,
    tenant_id           TEXT,
    stage_id            INTEGER NOT NULL,
    risk_tier           TEXT NOT NULL,
    passed              INTEGER NOT NULL,
    blocking_rule_ids   TEXT NOT NULL DEFAULT '[]',
    rule_versions       TEXT NOT NULL DEFAULT '{}',
    evaluated_at        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_gate_eval_tenant_time ON gate_evaluation_records (tenant_id, evaluated_at DESC);
CREATE INDEX IF NOT EXISTS idx_gate_eval_session ON gate_evaluation_records (session_id, stage_id);
"""


def _dt(value) -> str | None:
    """Serialize a datetime or string to ISO-8601 text for SQLite storage."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


class SQLiteSessionStore:
    """SQLite 会话持久化 — 零外部依赖，适用于演示 / 论文评估场景。"""

    def __init__(self, db_path: str | None = None):
        import os

        self._db_path = db_path or os.environ.get("SQLITE_PATH", _DEFAULT_DB_PATH)
        self._lock = threading.Lock()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def initialize(self) -> None:
        """Create tables inline — no Alembic needed."""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with self._get_conn() as conn:
                conn.executescript(_INIT_DDL)
                conn.commit()
        logger.info("SQLite schema initialized at %s", self._db_path)

    # ── Static helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _build_context_json_for_storage(ctx: ProjectContext) -> str:
        data = ctx.model_dump(mode="json")
        # Truncate to summaries — same logic as Postgres backend
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
                }
            )
        data["audit_events"] = truncated_audit

        truncated_reports = []
        for artifact in data.get("report_artifacts", []):
            truncated_reports.append(
                {
                    "report_id": artifact.get("report_id"),
                    "session_id": artifact.get("session_id"),
                    "version": artifact.get("version"),
                    "generated_at": artifact.get("generated_at"),
                }
            )
        data["report_artifacts"] = truncated_reports

        # T1.3: encrypt sensitive fields before serialization
        encrypt_fields_for_storage(data, ctx.data_classification)

        return json.dumps(data, default=str)

    @staticmethod
    def _truncate_snapshot(snapshot: dict | None, max_bytes: int = 50_000) -> dict | None:
        if snapshot is None:
            return None
        raw = json.dumps(snapshot, default=str)
        if len(raw.encode("utf-8")) <= max_bytes:
            return snapshot
        truncated: dict[str, Any] = {}
        for key, value in snapshot.items():
            val_str = json.dumps(value, default=str)
            if len(val_str.encode("utf-8")) > 5_000:
                truncated[key] = f"<truncated: {len(val_str)} bytes>"
            else:
                truncated[key] = value
        truncated["_truncated"] = True
        truncated["_original_size_bytes"] = len(raw.encode("utf-8"))
        return truncated

    @staticmethod
    def _truncate_report_content_json(content_json: dict) -> dict:
        truncated = dict(content_json)
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

    # ── Save helpers ──────────────────────────────────────────────────────────

    def _sync_human_actions(self, conn: sqlite3.Connection, ctx: ProjectContext) -> None:
        for action in ctx.pending_actions:
            conn.execute(
                """
                INSERT OR REPLACE INTO human_actions (
                    action_id, session_id, stage_id, node_id, source_type, source_id,
                    action_type, status, risk_level, title, description, trigger_reason,
                    blocking, payload_before, payload_after, reviewer_decision,
                    reviewer_note, stage_output_version, superseded_by,
                    action_contract_id, action_schema_version, idempotency_key,
                    target_stage, target_stage_version, target_object_path,
                    expected_before_hash, approved_payload_hash, resume_token, expires_at,
                    resolution_attempts, last_resolution_error, created_at, resolved_at
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                    int(action.blocking),
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
                    _dt(action.expires_at),
                    action.resolution_attempts,
                    action.last_resolution_error,
                    _dt(action.created_at),
                    _dt(action.resolved_at),
                ),
            )

    def _sync_action_resolution_logs(self, conn: sqlite3.Connection, ctx: ProjectContext) -> None:
        for log in getattr(ctx, "action_resolution_logs", []) or []:
            conn.execute(
                """
                INSERT OR IGNORE INTO action_resolution_logs (
                    log_id, session_id, action_id, idempotency_key, requested_status,
                    result_status, before_hash, after_hash, error_message, created_at
                )
                VALUES (?,?,?,?,?,?,?,?,?,?)
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
                    _dt(log.created_at),
                ),
            )

    def _sync_llm_traces(self, conn: sqlite3.Connection, ctx: ProjectContext) -> None:
        for trace in getattr(ctx, "llm_traces", []) or []:
            conn.execute(
                """
                INSERT OR IGNORE INTO llm_traces (
                    trace_id, session_id, stage, node_name, trace_type, provider, model,
                    prompt_template_id, prompt_template_version, input_token_count,
                    output_token_count, estimated_cost, latency_ms, retry_count,
                    parser_status, safety_status, evidence_count, error_type,
                    error_message, metadata, created_at
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                    _dt(trace.created_at),
                ),
            )

    def _sync_audit_events(self, conn: sqlite3.Connection, ctx: ProjectContext) -> None:
        for event in ctx.audit_events:
            conn.execute(
                """
                INSERT OR IGNORE INTO audit_events (
                    event_id, session_id, actor, event_type, target_type, target_id,
                    before_hash, after_hash, before_snapshot, after_snapshot, metadata, created_at
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
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
                    _dt(event.created_at),
                ),
            )

    def _sync_evidence_sources(self, conn: sqlite3.Connection, ctx: ProjectContext) -> None:
        for ev in ctx.evidence_sources:
            conn.execute(
                """
                INSERT OR REPLACE INTO evidence_sources (
                    evidence_id, session_id, title, url, source_type, credibility_score,
                    summary, claims, used_by_failure_mode_ids, verified, verified_by,
                    verified_at, verification_note, retrieved_at
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                    int(ev.verified),
                    ev.verified_by,
                    _dt(ev.verified_at),
                    ev.verification_note,
                    _dt(ev.retrieved_at),
                ),
            )

    def _sync_safety_findings(self, conn: sqlite3.Connection, ctx: ProjectContext) -> None:
        for finding in ctx.safety_findings:
            conn.execute(
                """
                INSERT OR REPLACE INTO safety_findings (
                    finding_id, session_id, stage_id, risk_type, severity, location,
                    description, recommended_action, requires_human_review, status,
                    taxonomy_refs, control_refs, mitigation_status, residual_risk,
                    resolution_note, resolved_at, created_at
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                    int(finding.requires_human_review),
                    finding.status,
                    json.dumps(getattr(finding, "taxonomy_refs", []), default=str),
                    json.dumps(getattr(finding, "control_refs", []), default=str),
                    getattr(finding, "mitigation_status", "open"),
                    getattr(finding, "residual_risk", "unknown"),
                    finding.resolution_note,
                    _dt(finding.resolved_at),
                    _dt(finding.created_at),
                ),
            )

    def _sync_report_artifacts(self, conn: sqlite3.Connection, ctx: ProjectContext) -> None:
        for artifact in ctx.report_artifacts:
            truncated = self._truncate_report_content_json(artifact.content_json)
            conn.execute(
                """
                INSERT OR REPLACE INTO report_artifacts (
                    report_id, session_id, version, content_json, content_markdown, generated_at
                )
                VALUES (?,?,?,?,?,?)
                """,
                (
                    artifact.report_id,
                    ctx.session_id,
                    artifact.version,
                    json.dumps(truncated, default=str),
                    artifact.content_markdown,
                    _dt(artifact.generated_at),
                ),
            )

    def _sync_eval_cases(self, conn: sqlite3.Connection, ctx: ProjectContext) -> None:
        for case in ctx.eval_cases:
            conn.execute(
                """
                INSERT OR REPLACE INTO eval_cases (
                    eval_id, session_id, stage_id, target_node_id, covered_failure_mode_ids,
                    scenario_type, source_type, source_trace_id, source_ref_id, metadata,
                    input_payload, expected_behavior, pass_criteria, actual_output, human_score,
                    human_comment, passed, created_at, scored_at
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                    int(case.passed) if case.passed is not None else None,
                    _dt(case.created_at),
                    _dt(case.scored_at),
                ),
            )

    def _sync_eval_runs(self, conn: sqlite3.Connection, ctx: ProjectContext) -> None:
        for run in ctx.eval_runs:
            conn.execute(
                """
                INSERT OR REPLACE INTO eval_runs (
                    run_id, session_id, eval_id, dataset_id, experiment_id, run_index,
                    target_node_id, covered_failure_mode_ids,
                    stage_output_version, run_mode, input_payload, expected_behavior,
                    actual_output, judge_result, judge_reason, judge_mode, violated_criteria,
                    status, error_message, trace_id, latency_ms, estimated_cost, created_at, completed_at
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                    _dt(run.created_at),
                    _dt(run.completed_at),
                ),
            )

    def _sync_eval_judgments(self, conn: sqlite3.Connection, ctx: ProjectContext) -> None:
        for judgment in getattr(ctx, "eval_judgments", []) or []:
            conn.execute(
                """
                INSERT OR REPLACE INTO eval_judgments (
                    judgment_id, session_id, eval_run_id, eval_id, experiment_id, judge_type,
                    judge_model, score, label, rationale, uncertainty, cited_rules, payload_json, created_at
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                    _dt(judgment.created_at),
                ),
            )

    def _sync_human_calibrations(self, conn: sqlite3.Connection, ctx: ProjectContext) -> None:
        for calibration in getattr(ctx, "human_calibrations", []) or []:
            conn.execute(
                """
                INSERT OR REPLACE INTO human_calibrations (
                    calibration_id, session_id, eval_run_id, eval_id, experiment_id, human_label,
                    human_comment, judge_label, agreement, disagreement_reason, reviewer_id,
                    payload_json, created_at
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                    int(calibration.agreement) if calibration.agreement is not None else None,
                    calibration.disagreement_reason,
                    calibration.reviewer_id,
                    json.dumps(calibration.model_dump(mode="json"), default=str),
                    _dt(calibration.created_at),
                ),
            )

    def _sync_eval_datasets(self, conn: sqlite3.Connection, ctx: ProjectContext) -> None:
        for dataset in getattr(ctx, "eval_datasets", []) or []:
            conn.execute(
                """
                INSERT OR REPLACE INTO eval_datasets (
                    dataset_id, session_id, name, version, source, stage, scenario_type,
                    case_ids, payload_json, created_at, updated_at
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
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
                    _dt(dataset.created_at),
                    _dt(dataset.updated_at),
                ),
            )

    def _sync_eval_experiments(self, conn: sqlite3.Connection, ctx: ProjectContext) -> None:
        for experiment in getattr(ctx, "eval_experiments", []) or []:
            conn.execute(
                """
                INSERT OR REPLACE INTO eval_experiments (
                    experiment_id, session_id, dataset_id, name, status, run_mode, provider,
                    model, baseline_experiment_id, eval_ids, run_ids, aggregate_metrics,
                    comparison_summary, payload_json, created_at, started_at, completed_at
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                    _dt(experiment.created_at),
                    _dt(experiment.started_at),
                    _dt(experiment.completed_at),
                ),
            )

    def _sync_redteam_cases(self, conn: sqlite3.Connection, ctx: ProjectContext) -> None:
        for case in getattr(ctx, "redteam_cases", []) or []:
            conn.execute(
                """
                INSERT OR REPLACE INTO redteam_cases (
                    redteam_case_id, session_id, target_stage, target_node_id,
                    source_finding_id, source_failure_mode_id, attack_type, severity,
                    status, linked_eval_case_id, taxonomy_refs, control_refs,
                    payload_json, created_at, approved_at, updated_at
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                    _dt(case.created_at),
                    _dt(case.approved_at),
                    _dt(case.updated_at),
                ),
            )

    def _sync_interrupt_records(self, conn: sqlite3.Connection, ctx: ProjectContext) -> None:
        for record in getattr(ctx, "interrupt_records", []) or []:
            conn.execute(
                """
                INSERT OR REPLACE INTO interrupt_records (
                    interrupt_id, session_id, action_id, stage_id, stage_output_version,
                    status, resume_value, thread_id, node_name, checkpoint_ns,
                    interrupt_payload, resume_consumed_at, created_at, resolved_at
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                    _dt(record.resume_consumed_at),
                    _dt(record.created_at),
                    _dt(record.resolved_at),
                ),
            )

    # ── Public API ────────────────────────────────────────────────────────────

    def save(self, ctx: ProjectContext) -> None:
        """Create or update a session."""
        ctx.updated_at = datetime.utcnow()
        now = _dt(ctx.updated_at)
        created = _dt(ctx.created_at)
        with self._lock:
            with self._get_conn() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO sessions
                        (session_id, tenant_id, current_state, context_json, created_at, updated_at)
                    VALUES (?,?,?,?,?,?)
                    """,
                    (
                        ctx.session_id,
                        ctx.tenant_id or None,
                        ctx.current_state.value,
                        self._build_context_json_for_storage(ctx),
                        created,
                        now,
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

    def load(self, session_id: str, tenant_id: str = "") -> ProjectContext | None:
        """Load a session; return None if not found or tenant mismatch."""
        with self._lock:
            with self._get_conn() as conn:
                if tenant_id:
                    row = conn.execute(
                        "SELECT context_json, tenant_id FROM sessions WHERE session_id=? AND tenant_id=?",
                        (session_id, tenant_id),
                    ).fetchone()
                else:
                    row = conn.execute(
                        "SELECT context_json, tenant_id FROM sessions WHERE session_id=?",
                        (session_id,),
                    ).fetchone()
        if not row:
            return None
        ctx = migrate_context(json.loads(row["context_json"]))
        if ctx:
            decrypt_fields_after_load(ctx)
            if row["tenant_id"]:
                ctx.tenant_id = row["tenant_id"]
        return ctx

    def archive_audit_events(self, session_id: str, purged_by: str, summary: dict) -> int:
        """Copy audit_events to audit_events_archive + write session_purged event.

        Returns the number of events archived (including the purge event).
        """
        import json
        import uuid

        archived = 0
        with self._lock:
            with self._get_conn() as conn:
                # Copy existing audit events
                rows = conn.execute(
                    "SELECT event_id, actor, event_type, target_type, target_id, "
                    "before_hash, after_hash, before_snapshot, after_snapshot, metadata, created_at "
                    "FROM audit_events WHERE session_id = ?",
                    (session_id,),
                ).fetchall()
                for row in rows:
                    conn.execute(
                        "INSERT OR IGNORE INTO audit_events_archive "
                        "(archive_id, original_session_id, event_id, actor, event_type, "
                        "target_type, target_id, before_hash, after_hash, before_snapshot, "
                        "after_snapshot, metadata, original_created_at, archived_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            f"arch-{row['event_id']}",
                            session_id,
                            row["event_id"],
                            row["actor"],
                            row["event_type"],
                            row["target_type"],
                            row["target_id"],
                            row["before_hash"],
                            row["after_hash"],
                            row["before_snapshot"],
                            row["after_snapshot"],
                            row["metadata"],
                            row["created_at"],
                            datetime.utcnow().isoformat(),
                        ),
                    )
                    archived += 1

                # Write session_purged event
                conn.execute(
                    "INSERT INTO audit_events_archive "
                    "(archive_id, original_session_id, event_id, actor, event_type, "
                    "target_type, target_id, before_hash, after_hash, before_snapshot, "
                    "after_snapshot, metadata, original_created_at, archived_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"arch-purged-{uuid.uuid4()}",
                        session_id,
                        f"purge-{uuid.uuid4()}",
                        purged_by,
                        "session_purged",
                        "session",
                        session_id,
                        None,
                        None,
                        None,
                        json.dumps(summary, default=str),
                        json.dumps({"purged_by": purged_by}, default=str),
                        datetime.utcnow().isoformat(),
                        datetime.utcnow().isoformat(),
                    ),
                )
                archived += 1
                conn.commit()
        return archived

    def delete(self, session_id: str, tenant_id: str = "") -> bool:
        """Delete a session row. Returns True if a row was deleted."""
        with self._lock:
            with self._get_conn() as conn:
                if tenant_id:
                    cur = conn.execute(
                        "DELETE FROM sessions WHERE session_id = ? AND tenant_id = ?",
                        (session_id, tenant_id),
                    )
                else:
                    cur = conn.execute(
                        "DELETE FROM sessions WHERE session_id = ?",
                        (session_id,),
                    )
                conn.commit()
                return cur.rowcount > 0

    def list_sessions(self, limit: int = 20, tenant_id: str = "") -> list[dict]:
        """Return recent sessions for the history list."""
        with self._lock:
            with self._get_conn() as conn:
                if tenant_id:
                    rows = conn.execute(
                        "SELECT session_id, current_state, created_at, updated_at, "
                        "json_extract(context_json,'$.research_target') AS research_target, "
                        "json_extract(context_json,'$.domain') AS domain "
                        "FROM sessions WHERE tenant_id=? ORDER BY updated_at DESC LIMIT ?",
                        (tenant_id, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT session_id, current_state, created_at, updated_at, "
                        "json_extract(context_json,'$.research_target') AS research_target, "
                        "json_extract(context_json,'$.domain') AS domain "
                        "FROM sessions ORDER BY updated_at DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
        return [dict(r) for r in rows]

    def log_event(
        self,
        session_id: str,
        event_type: str,
        stage: int | None,
        payload: dict,
    ) -> None:
        """Record a session event."""
        with self._lock:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT INTO session_events (session_id, event_type, stage, payload) VALUES (?,?,?,?)",
                    (session_id, event_type, stage, json.dumps(payload, default=str)),
                )
                conn.commit()

    def list_report_artifacts(self, session_id: str) -> list[dict]:
        with self._lock:
            with self._get_conn() as conn:
                rows = conn.execute(
                    "SELECT report_id, session_id, version, content_json, content_markdown, generated_at "
                    "FROM report_artifacts WHERE session_id=? ORDER BY generated_at DESC",
                    (session_id,),
                ).fetchall()
        artifacts: list[dict] = []
        for row in rows:
            content_raw = row["content_json"] or "{}"
            content = json.loads(content_raw) if isinstance(content_raw, str) else content_raw
            artifacts.append(
                {
                    "report_id": row["report_id"],
                    "session_id": row["session_id"],
                    "version": row["version"],
                    "generated_at": row["generated_at"],
                    "content_json": content,
                    "content_markdown": row["content_markdown"] or "",
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
        with self._lock:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT report_id, session_id, version, content_json, content_markdown, generated_at "
                    "FROM report_artifacts WHERE session_id=? AND report_id=?",
                    (session_id, report_id),
                ).fetchone()
        if not row:
            return None
        content_raw = row["content_json"] or "{}"
        content = json.loads(content_raw) if isinstance(content_raw, str) else content_raw
        return {
            "report_id": row["report_id"],
            "session_id": row["session_id"],
            "version": row["version"],
            "generated_at": row["generated_at"],
            "content_json": content,
            "content_markdown": row["content_markdown"] or "",
            "ai_generated": content.get("ai_generated", {}),
            "human_reviewed": content.get("human_reviewed", {}),
            "evidence": content.get("evidence_sources", []),
            "audit_events": content.get("audit_events", []),
            "open_risks": content.get("open_risks", []),
            "eval_summary": content.get("eval_summary", {}),
            "eval_runs": content.get("eval_runs", []),
            "failed_eval_runs": content.get("failed_eval_runs", []),
        }

    def list_interrupt_records(self, session_id: str) -> list[dict]:
        with self._lock:
            with self._get_conn() as conn:
                rows = conn.execute(
                    "SELECT interrupt_id, session_id, action_id, stage_id, stage_output_version, "
                    "status, resume_value, thread_id, node_name, checkpoint_ns, "
                    "interrupt_payload, resume_consumed_at, created_at, resolved_at "
                    "FROM interrupt_records WHERE session_id=? ORDER BY created_at DESC",
                    (session_id,),
                ).fetchall()
        return [dict(r) for r in rows]

    def get_interrupt_record(self, session_id: str, interrupt_id: str) -> dict | None:
        with self._lock:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT interrupt_id, session_id, action_id, stage_id, stage_output_version, "
                    "status, resume_value, thread_id, node_name, checkpoint_ns, "
                    "interrupt_payload, resume_consumed_at, created_at, resolved_at "
                    "FROM interrupt_records WHERE session_id=? AND interrupt_id=?",
                    (session_id, interrupt_id),
                ).fetchone()
        return dict(row) if row else None

    # ── Auth methods ──────────────────────────────────────────────────────────

    def create_tenant(self, name: str) -> dict:
        tenant_id = str(uuid.uuid4())
        with self._lock:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT INTO tenants (tenant_id, name) VALUES (?,?)",
                    (tenant_id, name),
                )
                row = conn.execute(
                    "SELECT tenant_id, name, created_at FROM tenants WHERE tenant_id=?",
                    (tenant_id,),
                ).fetchone()
                conn.commit()
        return dict(row)

    def create_user(
        self, tenant_id: str, email: str, password_hash: str, role: str = "viewer"
    ) -> dict:
        user_id = str(uuid.uuid4())
        with self._lock:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT INTO users (user_id, tenant_id, email, password_hash, role) VALUES (?,?,?,?,?)",
                    (user_id, tenant_id, email, password_hash, role),
                )
                row = conn.execute(
                    "SELECT user_id, tenant_id, email, role, created_at FROM users WHERE user_id=?",
                    (user_id,),
                ).fetchone()
                conn.commit()
        return dict(row)

    def get_user_by_email(self, email: str) -> dict | None:
        with self._lock:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT user_id, tenant_id, email, password_hash, role FROM users WHERE email=?",
                    (email,),
                ).fetchone()
        return dict(row) if row else None

    def count_users(self) -> int:
        with self._lock:
            with self._get_conn() as conn:
                row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
        return row["n"] if row else 0

    def list_users_by_tenant(self, tenant_id: str) -> list[dict]:
        with self._lock:
            with self._get_conn() as conn:
                rows = conn.execute(
                    "SELECT user_id, tenant_id, email, role, created_at "
                    "FROM users WHERE tenant_id=? ORDER BY created_at",
                    (tenant_id,),
                ).fetchall()
        return [dict(r) for r in rows]

    def update_user_role(self, user_id: str, tenant_id: str, new_role: str) -> dict | None:
        with self._lock:
            with self._get_conn() as conn:
                conn.execute(
                    "UPDATE users SET role=? WHERE user_id=? AND tenant_id=?",
                    (new_role, user_id, tenant_id),
                )
                row = conn.execute(
                    "SELECT user_id, tenant_id, email, role FROM users WHERE user_id=? AND tenant_id=?",
                    (user_id, tenant_id),
                ).fetchone()
                conn.commit()
        return dict(row) if row else None

    # ── Governance trend analytics (T3.2) ─────────────────────────────────────

    def record_gate_evaluation(
        self,
        *,
        session_id: str,
        tenant_id: str,
        stage_id: int,
        risk_tier: str,
        passed: bool,
        blocking_rule_ids: list,
        rule_versions: dict,
    ) -> None:
        """旁路写入单行评估记录——治理趋势数据源。"""
        record_id = str(uuid.uuid4())[:8]
        with self._lock:
            with self._get_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO gate_evaluation_records (
                        record_id, session_id, tenant_id, stage_id, risk_tier, passed,
                        blocking_rule_ids, rule_versions, evaluated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        record_id,
                        session_id,
                        tenant_id or None,
                        stage_id,
                        risk_tier,
                        int(passed),
                        json.dumps(blocking_rule_ids, default=str),
                        json.dumps(rule_versions, default=str),
                    ),
                )
                conn.commit()

    def gate_trends(self, tenant_id: str, weeks: int = 8) -> list[dict]:
        """按周聚合门禁评估趋势。空 tenant_id 不开放跨租户查询。"""
        if not tenant_id:
            return []
        from datetime import datetime, timedelta

        cutoff = (datetime.utcnow() - timedelta(weeks=weeks)).isoformat()
        with self._lock:
            with self._get_conn() as conn:
                rows = conn.execute(
                    """
                    SELECT strftime('%Y-W%W', evaluated_at) AS week,
                           passed,
                           blocking_rule_ids
                    FROM gate_evaluation_records
                    WHERE tenant_id = ? AND evaluated_at >= ?
                    ORDER BY week DESC
                    """,
                    (tenant_id, cutoff),
                ).fetchall()
        return _aggregate_gate_trends([dict(r) for r in rows])

    def governance_overview(self, tenant_id: str) -> dict:
        """租户内治理总览聚合。空 tenant_id 返回零值字典。"""
        zero = {
            "sessions_total": 0,
            "state_distribution": {},
            "risk_tier_distribution": {},
            "open_safety_findings": 0,
            "pending_actions": 0,
            "reports_exported": 0,
        }
        if not tenant_id:
            return zero
        with self._lock:
            with self._get_conn() as conn:
                state_rows = conn.execute(
                    "SELECT current_state, COUNT(*) AS n FROM sessions "
                    "WHERE tenant_id=? GROUP BY current_state",
                    (tenant_id,),
                ).fetchall()
                ctx_rows = conn.execute(
                    "SELECT session_id, context_json FROM sessions WHERE tenant_id=?",
                    (tenant_id,),
                ).fetchall()
                eval_rows = conn.execute(
                    "SELECT session_id, risk_tier, evaluated_at "
                    "FROM gate_evaluation_records WHERE tenant_id=?",
                    (tenant_id,),
                ).fetchall()
        return _aggregate_governance_overview(
            [dict(r) for r in state_rows],
            [dict(r) for r in ctx_rows],
            [dict(r) for r in eval_rows],
            zero,
        )

    def actions_backlog(self, tenant_id: str, limit: int = 50) -> list[dict]:
        """待处理人工动作明细，按 risk_level + 等待时长排序。空 tenant_id 返回空列表。"""
        if not tenant_id:
            return []
        with self._lock:
            with self._get_conn() as conn:
                rows = conn.execute(
                    "SELECT session_id, context_json FROM sessions WHERE tenant_id=?",
                    (tenant_id,),
                ).fetchall()
        return _aggregate_actions_backlog([dict(r) for r in rows], limit)


def _aggregate_gate_trends(rows: list[dict]) -> list[dict]:
    """Shared weekly-bucket aggregation for gate_trends."""
    from collections import Counter

    buckets: dict[str, dict] = {}
    for row in rows:
        week = row["week"]
        bucket = buckets.setdefault(week, {"evaluations": 0, "passed": 0, "rules": []})
        bucket["evaluations"] += 1
        if row["passed"]:
            bucket["passed"] += 1
        br_ids = row["blocking_rule_ids"]
        if isinstance(br_ids, str):
            br_ids = json.loads(br_ids) if br_ids else []
        bucket["rules"].extend(br_ids or [])

    result = []
    for week, data in sorted(buckets.items(), reverse=True):
        evaluations = data["evaluations"]
        passed = data["passed"]
        rule_counts = Counter(data["rules"]).most_common(5)
        result.append(
            {
                "week": week,
                "evaluations": evaluations,
                "passed": passed,
                "pass_rate": passed / evaluations if evaluations else 0.0,
                "top_blocking_rules": [{"rule_id": r, "count": c} for r, c in rule_counts],
            }
        )
    return result


def _aggregate_governance_overview(
    state_rows: list[dict], ctx_rows: list[dict], eval_rows: list[dict], zero: dict
) -> dict:
    """Shared governance-overview aggregation."""
    state_distribution: dict[str, int] = {}
    sessions_total = 0
    for row in state_rows:
        state = row["current_state"]
        cnt = row["n"]
        state_distribution[state] = cnt
        sessions_total += cnt

    # risk_tier_distribution: latest risk_tier per session
    latest_by_session: dict[str, tuple] = {}
    for row in eval_rows:
        sid = row["session_id"]
        evaluated_at = row["evaluated_at"]
        cur = latest_by_session.get(sid)
        if cur is None or evaluated_at > cur[0]:
            latest_by_session[sid] = (evaluated_at, row["risk_tier"])
    risk_tier_distribution: dict[str, int] = {}
    for _, tier in latest_by_session.values():
        risk_tier_distribution[tier] = risk_tier_distribution.get(tier, 0) + 1

    open_safety_findings = 0
    pending_actions = 0
    reports_exported = 0
    for row in ctx_rows:
        raw = row.get("context_json") or "{}"
        ctx_data = json.loads(raw) if isinstance(raw, str) else raw
        for finding in ctx_data.get("safety_findings", []) or []:
            if finding.get("status") == "open":
                open_safety_findings += 1
        for action in ctx_data.get("pending_actions", []) or []:
            if action.get("status") == "pending":
                pending_actions += 1
        if ctx_data.get("report_artifacts"):
            reports_exported += 1

    return {
        "sessions_total": sessions_total,
        "state_distribution": state_distribution,
        "risk_tier_distribution": risk_tier_distribution,
        "open_safety_findings": open_safety_findings,
        "pending_actions": pending_actions,
        "reports_exported": reports_exported,
    }


def _aggregate_actions_backlog(rows: list[dict], limit: int) -> list[dict]:
    """Shared actions-backlog aggregation."""
    risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    actions: list[dict] = []
    for row in rows:
        session_id = row["session_id"]
        raw = row.get("context_json") or "{}"
        ctx_data = json.loads(raw) if isinstance(raw, str) else raw
        for action in ctx_data.get("pending_actions", []) or []:
            if action.get("status") == "pending":
                actions.append(
                    {
                        "session_id": session_id,
                        "action_id": action.get("action_id"),
                        "title": action.get("title"),
                        "risk_level": action.get("risk_level", "medium"),
                        "stage_id": action.get("stage_id"),
                        "created_at": action.get("created_at"),
                    }
                )
    actions.sort(key=lambda a: (risk_order.get(a["risk_level"], 4), a.get("created_at") or ""))
    return actions[:limit]
