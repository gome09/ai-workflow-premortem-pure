# storage/backends/postgres.py
"""PostgreSQL session-store backend (moved from storage/session_store.py)."""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from functools import wraps
from typing import Any, ParamSpec, TypeAlias, TypeVar, cast

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from core.config import settings
from core.migrations import migrate_context
from core.models import ProjectContext
from core.workflow_state_service import sanitize_persisted_state
from storage.access import SystemAccess, resolve_system_access
from storage.context_digest import compute_context_digest
from storage.errors import StaleContextError, TenantIsolationError
from storage.field_security import (
    decrypt_fields_after_load,
    decrypt_text_field,
    encrypt_fields_for_storage,
    encrypt_json_field,
    encrypt_text_field,
    is_encryption_enabled,
)
from storage.goal_backfill import GoalBackfillMode, transform_goal_context
from storage.projection_read import build_projection_rows, get_projection_spec
from storage.projection_state import compute_state, plan_sync

logger = logging.getLogger(__name__)

# 连接固定使用 dict_row 行工厂，行对象按列名索引；所有查询/_sync_* 方法均依赖此形状。
DictConnection: TypeAlias = psycopg.Connection[dict[str, Any]]

# 治理统计口径：真实业务会话参与聚合，内置场景演示会话一律排除。
# 依赖 V008 生成列（data_classification / selected_scenario_id），避免 JSONB 全表求值。
# 谓词显式内联在每条常量 SQL 中；租户值只通过参数绑定传入。
_GOV_STATE_SQL = """
    SELECT s.current_state, COUNT(*) AS n FROM sessions AS s
    WHERE s.tenant_id = %s::uuid
      AND COALESCE(s.data_classification, 'business_internal') <> 'public_demo'
      AND NULLIF(s.selected_scenario_id, '') IS NULL
    GROUP BY s.current_state
"""
_GOV_EVAL_SQL = """
    SELECT ger.session_id, ger.risk_tier, ger.evaluated_at
    FROM gate_evaluation_records AS ger
    JOIN sessions AS s ON s.session_id = ger.session_id
    WHERE ger.tenant_id = %s AND s.tenant_id = %s::uuid
      AND COALESCE(s.data_classification, 'business_internal') <> 'public_demo'
      AND NULLIF(s.selected_scenario_id, '') IS NULL
"""
_GOV_FINDING_SQL = """
    SELECT COUNT(*) AS n
    FROM safety_findings AS sf
    JOIN sessions AS s ON s.session_id = sf.session_id
    WHERE s.tenant_id = %s::uuid
      AND sf.status = 'open'
      AND COALESCE(s.data_classification, 'business_internal') <> 'public_demo'
      AND NULLIF(s.selected_scenario_id, '') IS NULL
"""
_GOV_ACTION_SQL = """
    SELECT COUNT(*) AS n
    FROM human_actions AS ha
    JOIN sessions AS s ON s.session_id = ha.session_id
    WHERE s.tenant_id = %s::uuid
      AND ha.status = 'pending'
      AND COALESCE(s.data_classification, 'business_internal') <> 'public_demo'
      AND NULLIF(s.selected_scenario_id, '') IS NULL
"""
_GOV_REPORT_SQL = """
    SELECT COUNT(DISTINCT ra.session_id) AS n
    FROM report_artifacts AS ra
    JOIN sessions AS s ON s.session_id = ra.session_id
    WHERE s.tenant_id = %s::uuid
      AND COALESCE(s.data_classification, 'business_internal') <> 'public_demo'
      AND NULLIF(s.selected_scenario_id, '') IS NULL
"""
_GOV_DEMO_SQL = """
    SELECT COUNT(*) AS n FROM sessions AS s
    WHERE s.tenant_id = %s::uuid
      AND (
          COALESCE(s.data_classification, 'business_internal') = 'public_demo'
          OR NULLIF(s.selected_scenario_id, '') IS NOT NULL
      )
"""
_GOV_BACKLOG_SQL = """
    SELECT ha.session_id, ha.action_id, ha.title, ha.risk_level,
           ha.stage_id, ha.created_at
    FROM human_actions AS ha
    JOIN sessions AS s ON s.session_id = ha.session_id
    WHERE s.tenant_id = %s::uuid
      AND ha.status = 'pending'
      AND COALESCE(s.data_classification, 'business_internal') <> 'public_demo'
      AND NULLIF(s.selected_scenario_id, '') IS NULL
"""
_GOV_METRICS_STATE_SQL = """
    SELECT s.current_state, COUNT(*) AS n FROM sessions AS s
    WHERE COALESCE(s.data_classification, 'business_internal') <> 'public_demo'
      AND NULLIF(s.selected_scenario_id, '') IS NULL
    GROUP BY s.current_state
"""
_GOV_METRICS_RISK_SQL = """
    SELECT ha.risk_level, COUNT(*) AS n
    FROM human_actions AS ha
    JOIN sessions AS s ON s.session_id = ha.session_id
    WHERE ha.status = 'pending'
      AND COALESCE(s.data_classification, 'business_internal') <> 'public_demo'
      AND NULLIF(s.selected_scenario_id, '') IS NULL
    GROUP BY ha.risk_level
"""

P = ParamSpec("P")
R = TypeVar("R")


def _executemany(conn: DictConnection, sql: str, rows: list[tuple[Any, ...]]) -> None:
    """psycopg3 的 executemany 位于 cursor 上，统一封装一次。"""
    with conn.cursor() as cur:
        cur.executemany(sql, rows)


def _record_db_operation(operation: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """记录存储层操作耗时；指标模块缺失或打点失败均不影响主路径。"""

    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        @wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            started = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                try:
                    from api.metrics import observe_db_operation

                    observe_db_operation(operation, time.perf_counter() - started)
                except Exception:
                    logger.debug("db operation metric failed; non-fatal", exc_info=True)

        return wrapper

    return decorator


class PostgresSessionStore:
    """PostgreSQL 会话持久化"""

    # TODO: _sync_* 方法太多且结构重复，后面应该抽象一个通用的 upsert 方法
    # 不过现在能用就没急着改

    def __init__(self):
        self._dsn = settings.postgres_dsn_sync
        self._pool: ConnectionPool[DictConnection] | None = None
        self._pool_lock = threading.Lock()

    def _connect_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"row_factory": dict_row}
        timeout_ms = int(settings.db_statement_timeout_ms)
        if timeout_ms > 0:
            kwargs["options"] = f"-c statement_timeout={timeout_ms}"
        return kwargs

    def _get_pool(self) -> ConnectionPool[DictConnection] | None:
        """惰性创建连接池；创建失败时降级为单连接模式并告警。"""
        if self._pool is not None:
            return self._pool
        with self._pool_lock:
            if self._pool is None:
                try:
                    self._pool = ConnectionPool(
                        conninfo=self._dsn,
                        min_size=int(settings.db_pool_min_size),
                        max_size=int(settings.db_pool_max_size),
                        timeout=float(settings.db_pool_timeout_seconds),
                        kwargs=self._connect_kwargs(),
                        open=True,
                    )
                except Exception:
                    logger.warning(
                        "PostgreSQL connection pool init failed; falling back to "
                        "per-request connections",
                        exc_info=True,
                    )
                    return None
        return self._pool

    @contextmanager
    def _get_conn(self) -> Iterator[DictConnection]:
        """Yield a pooled connection (committed on exit) or a single connection."""
        pool = self._get_pool()
        if pool is not None:
            with pool.connection() as conn:
                yield conn
            return
        # row_factory=dict_row 是关键约束：所有查询与 _sync_* 方法都按列名索引行对象。
        with psycopg.connect(self._dsn, **self._connect_kwargs()) as conn:
            yield conn

    def close(self) -> None:
        """Release pooled connections (called at application shutdown)."""
        with self._pool_lock:
            if self._pool is not None:
                self._pool.close()
                self._pool = None

    @_record_db_operation("backfill_goal")
    def backfill_goal_encryption(
        self,
        *,
        dry_run: bool = True,
        verify_only: bool = False,
        decrypt: bool = False,
        session_ids: list[str] | None = None,
        batch_size: int = 100,
    ) -> dict[str, Any]:
        """Backfill the historical plaintext ``goal`` field (PostgreSQL).

        Modes: encrypt (default), verify_only, decrypt (rollback helper).
        The sweep is idempotent and uses ``context_json::text`` identity as the
        optimistic conflict check; it is intended to run while traffic is
        drained or during a maintenance window.
        """
        if verify_only and decrypt:
            raise ValueError("verify_only and decrypt are mutually exclusive")
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        if not is_encryption_enabled():
            raise RuntimeError("DATA_ENCRYPTION_KEY is not configured")
        mode: GoalBackfillMode = "verify" if verify_only else ("decrypt" if decrypt else "encrypt")
        result: dict[str, Any] = {
            "mode": mode,
            "dry_run": dry_run,
            "scanned": 0,
            "changed": 0,
            "conflicts": 0,
            "status_counts": {},
            "errors": [],
        }

        with self._get_conn() as conn:
            if session_ids:
                sql = (
                    "SELECT session_id::text AS session_id, context_json::text AS context_text "
                    "FROM sessions WHERE session_id = ANY(%s) ORDER BY session_id"
                )
                params: tuple[Any, ...] = (list(session_ids),)
            else:
                sql = (
                    "SELECT session_id::text AS session_id, context_json::text AS context_text "
                    "FROM sessions ORDER BY session_id"
                )
                params = ()
            cursor = conn.execute(sql, params)
            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break
                for row in rows:
                    result["scanned"] += 1
                    transform = transform_goal_context(row["context_text"], mode=mode)
                    status_counts = result["status_counts"]
                    status_counts[transform.status] = status_counts.get(transform.status, 0) + 1
                    if transform.error:
                        if len(result["errors"]) < 20:
                            result["errors"].append(
                                {"session_id": row["session_id"], "error": transform.error}
                            )
                    if not transform.changed:
                        continue
                    result["changed"] += 1
                    if dry_run or verify_only:
                        continue
                    updated = conn.execute(
                        "UPDATE sessions SET context_json = %s::jsonb "
                        "WHERE session_id = %s AND context_json::text = %s",
                        (transform.context_json, row["session_id"], row["context_text"]),
                    )
                    if updated.rowcount == 0:
                        result["conflicts"] += 1
            if not dry_run and not verify_only:
                conn.commit()
        return result

    def initialize(self) -> None:
        """Run alembic migrations to head. Called once at app startup."""
        import shutil
        import subprocess
        import sys

        alembic_bin = shutil.which("alembic") or str(
            __import__("pathlib").Path(sys.executable).parent / "alembic"
        )
        # 多 worker（UVICORN_WORKERS>1）并发启动时每个 worker 都会执行本方法；
        # 用 Postgres advisory lock 串行化，避免并发 alembic upgrade 竞态创建
        # alembic_version 表（pg_type_typname_nsp_index UniqueViolation）。
        _MIGRATION_LOCK_KEY = 0x61697766  # "aiwf"
        with psycopg.connect(self._dsn) as lock_conn:
            lock_conn.execute("SELECT pg_advisory_lock(%s)", (_MIGRATION_LOCK_KEY,))
            try:
                result = subprocess.run(  # noqa: S603  # alembic command, input is controlled
                    [alembic_bin, "upgrade", "head"],
                    capture_output=True,
                    text=True,
                )
            finally:
                lock_conn.execute("SELECT pg_advisory_unlock(%s)", (_MIGRATION_LOCK_KEY,))
        if result.returncode != 0:
            logger.error("Alembic migration failed: %s", result.stderr)
            raise RuntimeError(f"Database migration failed:\n{result.stderr}")
        logger.info("Database migrations applied. %s", result.stdout.strip())

    @staticmethod
    def _build_context_json_for_storage(
        ctx: ProjectContext, data: dict[str, Any] | None = None
    ) -> str:
        """序列化 context_json，截断大字段以避免超过 PostgreSQL JSONB 256MB 限制。

        LLM traces、eval runs、audit events 等已通过 _sync_* 方法写入独立表，
        context_json 只保留摘要信息。save() 传入同一次 model_dump 结果，
        投影哈希已在截断/加密前计算。
        """
        data = dict(data) if data is not None else ctx.model_dump(mode="json")

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

        # T1.3: encrypt sensitive fields before serialization
        encrypt_fields_for_storage(data, ctx.data_classification)

        return json.dumps(data, default=str)

    @_record_db_operation("save")
    def save(self, ctx: ProjectContext) -> None:
        """创建或更新会话。

        PostgreSQL 下强制两项正确性约束：
        - 租户一致：已有会话的 tenant_id 必须与待保存上下文一致，防止跨租户覆盖。
        - 乐观锁：保存时校验 `_storage_version`，并发保存不会静默丢失更新。
        """
        ctx.updated_at = datetime.utcnow()
        data = ctx.model_dump(mode="json")
        # updated_at 只落 sessions 列：若留在 context_json，每次保存都会改变
        # 内容指纹，写放大保护就失效了。
        data.pop("updated_at", None)
        current_state = compute_state(data)
        state_json = json.dumps(current_state, default=str)
        digest = compute_context_digest(data)
        context_json = self._build_context_json_for_storage(ctx, data)
        expected_version = int(getattr(ctx, "_storage_version", 0))
        incoming_tenant = ctx.tenant_id or ""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT version, tenant_id::text, projection_state, context_digest "
                "FROM sessions WHERE session_id = %s FOR UPDATE",
                (ctx.session_id,),
            ).fetchone()
            previous_state = row.get("projection_state") if row else None
            plans = plan_sync(previous_state, current_state, data)
            if row is None:
                conn.execute(
                    """
                    INSERT INTO sessions (
                        session_id, tenant_id, current_state, context_json, projection_state,
                        context_digest, created_at, updated_at, version
                    )
                    VALUES (%s, %s::uuid, %s, %s, %s::jsonb, %s, %s, %s, 0)
                    """,
                    (
                        ctx.session_id,
                        ctx.tenant_id or None,
                        str(data.get("current_state") or "init"),
                        context_json,
                        state_json,
                        digest,
                        ctx.created_at,
                        ctx.updated_at,
                    ),
                )
                new_version = 0
            else:
                existing_tenant = row.get("tenant_id") or ""
                if existing_tenant != incoming_tenant:
                    raise TenantIsolationError(ctx.session_id, "save")
                current_version = int(row.get("version") or 0)
                if current_version != expected_version:
                    raise StaleContextError(ctx.session_id, expected_version, current_version)
                if (row.get("context_digest") or "") == digest:
                    # 内容未变化：只推进版本/状态，不重写整份 context_json（TOAST 列）。
                    conn.execute(
                        """
                        UPDATE sessions
                        SET current_state    = %s,
                            projection_state = %s::jsonb,
                            updated_at       = %s,
                            version          = version + 1
                        WHERE session_id = %s
                        """,
                        (
                            str(data.get("current_state") or "init"),
                            state_json,
                            ctx.updated_at,
                            ctx.session_id,
                        ),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE sessions
                        SET current_state    = %s,
                            context_json     = %s,
                            projection_state = %s::jsonb,
                            context_digest   = %s,
                            updated_at       = %s,
                            version          = version + 1
                        WHERE session_id = %s
                        """,
                        (
                            str(data.get("current_state") or "init"),
                            context_json,
                            state_json,
                            digest,
                            ctx.updated_at,
                            ctx.session_id,
                        ),
                    )
                new_version = current_version + 1
            if not plans["human_actions"].skip:
                self._sync_human_actions(conn, ctx)
            plan = plans["action_resolution_logs"]
            if not plan.skip:
                self._sync_action_resolution_logs(conn, ctx, start=plan.start)
            plan = plans["llm_traces"]
            if not plan.skip:
                self._sync_llm_traces(conn, ctx, start=plan.start)
            plan = plans["audit_events"]
            if not plan.skip:
                self._sync_audit_events(conn, ctx, start=plan.start)
            if not plans["evidence_sources"].skip:
                self._sync_evidence_sources(conn, ctx)
            if not plans["safety_findings"].skip:
                self._sync_safety_findings(conn, ctx)
            if not plans["report_artifacts"].skip:
                self._sync_report_artifacts(conn, ctx)
            if not plans["eval_cases"].skip:
                self._sync_eval_cases(conn, ctx)
            if not plans["eval_runs"].skip:
                self._sync_eval_runs(conn, ctx)
            if not plans["eval_judgments"].skip:
                self._sync_eval_judgments(conn, ctx)
            if not plans["human_calibrations"].skip:
                self._sync_human_calibrations(conn, ctx)
            if not plans["eval_datasets"].skip:
                self._sync_eval_datasets(conn, ctx)
            if not plans["eval_experiments"].skip:
                self._sync_eval_experiments(conn, ctx)
            if not plans["redteam_cases"].skip:
                self._sync_redteam_cases(conn, ctx)
            if not plans["interrupt_records"].skip:
                self._sync_interrupt_records(conn, ctx)
            # outbox 行量很小，每次同步以保持 pending → completed 状态推进。
            self._sync_interrupt_resume_outbox(conn, ctx)
            conn.commit()
        # 只有事务提交成功后才回写版本，异常路径保持原版本以便调用方重试。
        ctx._storage_version = new_version

    def _sync_interrupt_resume_outbox(self, conn: DictConnection, ctx: ProjectContext) -> None:
        rows: list[tuple[Any, ...]] = []
        for record in getattr(ctx, "interrupt_records", []) or []:
            if record.status != "resumed" or record.resume_consumed_at is not None:
                continue
            rows.append(
                (
                    record.interrupt_id,
                    ctx.session_id,
                    ctx.tenant_id or None,
                    record.action_id,
                    record.thread_id,
                    record.checkpoint_ns,
                    json.dumps(record.resume_value or {}, default=str),
                )
            )
        if not rows:
            return
        _executemany(
            conn,
            """
            INSERT INTO interrupt_resume_outbox (
                interrupt_id, session_id, tenant_id, action_id, thread_id,
                checkpoint_ns, resume_payload, status, updated_at
            ) VALUES (%s, %s, %s::uuid, %s, %s, %s, %s, 'pending', NOW())
            ON CONFLICT (action_id) DO UPDATE SET
                interrupt_id = EXCLUDED.interrupt_id,
                thread_id = EXCLUDED.thread_id,
                checkpoint_ns = EXCLUDED.checkpoint_ns,
                resume_payload = EXCLUDED.resume_payload,
                updated_at = NOW(),
                status = CASE
                    WHEN interrupt_resume_outbox.status = 'completed' THEN 'completed'
                    ELSE interrupt_resume_outbox.status
                END
            """,
            rows,
        )

    def _sync_human_actions(self, conn: DictConnection, ctx: ProjectContext) -> None:
        """同步 ProjectContext 中的人工动作到索引表。使用 upsert，避免删除历史。"""
        classification = ctx.data_classification
        rows = [
            (
                action.action_id,
                ctx.session_id,
                ctx.tenant_id or None,
                action.stage_id,
                action.node_id,
                action.source_type,
                action.source_id,
                action.action_type,
                action.status,
                action.risk_level,
                encrypt_text_field(action.title, classification),
                encrypt_text_field(action.description, classification),
                encrypt_text_field(action.trigger_reason, classification),
                action.blocking,
                encrypt_json_field(action.payload_before, classification),
                encrypt_json_field(action.payload_after, classification),
                action.reviewer_decision,
                encrypt_text_field(action.reviewer_note, classification),
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
            )
            for action in ctx.pending_actions
        ]
        if not rows:
            return
        _executemany(
            conn,
            """
            INSERT INTO human_actions (
                action_id, session_id, tenant_id, stage_id, node_id, source_type, source_id,
                action_type, status, risk_level, title, description, trigger_reason,
                blocking, payload_before, payload_after, reviewer_decision,
                reviewer_note, stage_output_version, superseded_by,
                action_contract_id, action_schema_version, idempotency_key,
                target_stage, target_stage_version, target_object_path,
                expected_before_hash, approved_payload_hash, resume_token, expires_at,
                resolution_attempts, last_resolution_error, created_at, resolved_at
            )
            VALUES (
                %s, %s, %s::uuid, %s, %s, %s, %s,
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
            rows,
        )

    def _sync_action_resolution_logs(
        self, conn: DictConnection, ctx: ProjectContext, start: int = 0
    ) -> None:
        """同步 action resolution logs。append-only：已存在 log_id 不覆盖。"""
        rows = [
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
            )
            for log in (getattr(ctx, "action_resolution_logs", []) or [])[start:]
        ]
        if not rows:
            return
        _executemany(
            conn,
            """
            INSERT INTO action_resolution_logs (
                log_id, session_id, action_id, idempotency_key, requested_status,
                result_status, before_hash, after_hash, error_message, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (log_id) DO NOTHING
            """,
            rows,
        )

    def _sync_llm_traces(self, conn: DictConnection, ctx: ProjectContext, start: int = 0) -> None:
        """同步 LLM traces。append-only：已存在 trace_id 不覆盖。"""
        rows = [
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
            )
            for trace in (getattr(ctx, "llm_traces", []) or [])[start:]
        ]
        if not rows:
            return
        _executemany(
            conn,
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
            rows,
        )

    @staticmethod
    def _truncate_snapshot(snapshot: dict | None, max_bytes: int = 50_000) -> dict | None:
        """Truncate a snapshot dict if its JSON representation exceeds max_bytes."""
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

    def _sync_audit_events(self, conn: DictConnection, ctx: ProjectContext, start: int = 0) -> None:
        """同步审计事件。append-only：已存在 event_id 不覆盖、不删除。"""
        rows = [
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
            )
            for event in ctx.audit_events[start:]
        ]
        if not rows:
            return
        _executemany(
            conn,
            """
            INSERT INTO audit_events (
                event_id, session_id, actor, event_type, target_type, target_id,
                before_hash, after_hash, before_snapshot, after_snapshot, metadata, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (event_id) DO NOTHING
            """,
            rows,
        )

    def _sync_evidence_sources(self, conn: DictConnection, ctx: ProjectContext) -> None:
        classification = ctx.data_classification
        rows = [
            (
                ev.evidence_id,
                ctx.session_id,
                ev.title,
                ev.url,
                ev.source_type,
                ev.credibility_score,
                encrypt_text_field(ev.summary, classification),
                encrypt_json_field(ev.claims, classification),
                json.dumps(ev.used_by_failure_mode_ids, default=str),
                ev.verified,
                ev.verified_by,
                ev.verified_at,
                ev.verification_note,
                ev.retrieved_at,
            )
            for ev in ctx.evidence_sources
        ]
        if not rows:
            return
        _executemany(
            conn,
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
            rows,
        )

    def _sync_safety_findings(self, conn: DictConnection, ctx: ProjectContext) -> None:
        rows = [
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
            )
            for finding in ctx.safety_findings
        ]
        if not rows:
            return
        _executemany(
            conn,
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
            rows,
        )

    @staticmethod
    def _truncate_report_content_json(content_json: dict) -> dict:
        """Truncate large fields in report content_json for DB storage."""
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

    def _sync_report_artifacts(self, conn: DictConnection, ctx: ProjectContext) -> None:
        classification = ctx.data_classification
        rows = [
            (
                artifact.report_id,
                ctx.session_id,
                artifact.version,
                encrypt_json_field(
                    self._truncate_report_content_json(artifact.content_json), classification
                ),
                encrypt_text_field(artifact.content_markdown, classification),
                artifact.generated_at,
            )
            for artifact in ctx.report_artifacts
        ]
        if not rows:
            return
        _executemany(
            conn,
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
            rows,
        )

    def _sync_eval_cases(self, conn: DictConnection, ctx: ProjectContext) -> None:
        rows = [
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
                case.standard_version,
                case.actual_output,
                case.human_score,
                case.human_comment,
                case.passed,
                case.created_at,
                case.scored_at,
            )
            for case in ctx.eval_cases
        ]
        if not rows:
            return
        _executemany(
            conn,
            """
            INSERT INTO eval_cases (
                eval_id, session_id, stage_id, target_node_id, covered_failure_mode_ids,
                scenario_type, source_type, source_trace_id, source_ref_id, metadata,
                input_payload, expected_behavior, pass_criteria, standard_version,
                actual_output, human_score,
                human_comment, passed, created_at, scored_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (eval_id) DO UPDATE SET
                covered_failure_mode_ids = EXCLUDED.covered_failure_mode_ids,
                source_type = EXCLUDED.source_type,
                source_trace_id = EXCLUDED.source_trace_id,
                source_ref_id = EXCLUDED.source_ref_id,
                metadata = EXCLUDED.metadata,
                pass_criteria = EXCLUDED.pass_criteria,
                standard_version = EXCLUDED.standard_version,
                actual_output = EXCLUDED.actual_output,
                human_score = EXCLUDED.human_score,
                human_comment = EXCLUDED.human_comment,
                passed = EXCLUDED.passed,
                scored_at = EXCLUDED.scored_at
            """,
            rows,
        )

    def _sync_eval_runs(self, conn: DictConnection, ctx: ProjectContext) -> None:
        rows = [
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
                run.execution_kind,
                run.execution_outcome,
                run.evaluation_version_digest,
                run.target_endpoint,
                run.target_deployment_version,
                run.case_version_digest,
                run.input_payload,
                run.expected_behavior,
                run.actual_output,
                run.judge_result,
                run.judge_reason,
                run.judge_mode,
                json.dumps(run.violated_criteria, default=str),
                json.dumps(run.pass_criteria, default=str),
                json.dumps(run.llm_judge_suggestion, default=str)
                if run.llm_judge_suggestion is not None
                else None,
                run.status,
                run.error_message,
                run.trace_id,
                run.latency_ms,
                run.estimated_cost,
                run.created_at,
                run.completed_at,
            )
            for run in ctx.eval_runs
        ]
        if not rows:
            return
        _executemany(
            conn,
            """
            INSERT INTO eval_runs (
                run_id, session_id, eval_id, dataset_id, experiment_id, run_index,
                target_node_id, covered_failure_mode_ids,
                stage_output_version, run_mode,
                execution_kind, execution_outcome, evaluation_version_digest,
                target_endpoint, target_deployment_version, case_version_digest,
                input_payload, expected_behavior,
                actual_output, judge_result, judge_reason, judge_mode, violated_criteria,
                pass_criteria, llm_judge_suggestion,
                status, error_message, trace_id, latency_ms, estimated_cost, created_at, completed_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id) DO UPDATE SET
                dataset_id = EXCLUDED.dataset_id,
                experiment_id = EXCLUDED.experiment_id,
                run_index = EXCLUDED.run_index,
                execution_kind = EXCLUDED.execution_kind,
                execution_outcome = EXCLUDED.execution_outcome,
                evaluation_version_digest = EXCLUDED.evaluation_version_digest,
                target_endpoint = EXCLUDED.target_endpoint,
                target_deployment_version = EXCLUDED.target_deployment_version,
                case_version_digest = EXCLUDED.case_version_digest,
                actual_output = EXCLUDED.actual_output,
                judge_result = EXCLUDED.judge_result,
                judge_reason = EXCLUDED.judge_reason,
                judge_mode = EXCLUDED.judge_mode,
                violated_criteria = EXCLUDED.violated_criteria,
                pass_criteria = EXCLUDED.pass_criteria,
                llm_judge_suggestion = EXCLUDED.llm_judge_suggestion,
                status = EXCLUDED.status,
                error_message = EXCLUDED.error_message,
                trace_id = EXCLUDED.trace_id,
                latency_ms = EXCLUDED.latency_ms,
                estimated_cost = EXCLUDED.estimated_cost,
                completed_at = EXCLUDED.completed_at
            """,
            rows,
        )

    def _sync_eval_judgments(self, conn: DictConnection, ctx: ProjectContext) -> None:
        rows = [
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
            )
            for judgment in getattr(ctx, "eval_judgments", []) or []
        ]
        if not rows:
            return
        _executemany(
            conn,
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
            rows,
        )

    def _sync_human_calibrations(self, conn: DictConnection, ctx: ProjectContext) -> None:
        rows = [
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
            )
            for calibration in getattr(ctx, "human_calibrations", []) or []
        ]
        if not rows:
            return
        _executemany(
            conn,
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
            rows,
        )

    def _sync_eval_datasets(self, conn: DictConnection, ctx: ProjectContext) -> None:
        rows = [
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
            )
            for dataset in getattr(ctx, "eval_datasets", []) or []
        ]
        if not rows:
            return
        _executemany(
            conn,
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
            rows,
        )

    def _sync_eval_experiments(self, conn: DictConnection, ctx: ProjectContext) -> None:
        rows = [
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
            )
            for experiment in getattr(ctx, "eval_experiments", []) or []
        ]
        if not rows:
            return
        _executemany(
            conn,
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
            rows,
        )

    def _sync_redteam_cases(self, conn: DictConnection, ctx: ProjectContext) -> None:
        rows = [
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
            )
            for case in getattr(ctx, "redteam_cases", []) or []
        ]
        if not rows:
            return
        _executemany(
            conn,
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
            rows,
        )

    def _sync_interrupt_records(self, conn: DictConnection, ctx: ProjectContext) -> None:
        """同步业务中断记录。"""
        rows = [
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
            )
            for record in getattr(ctx, "interrupt_records", []) or []
        ]
        if not rows:
            return
        _executemany(
            conn,
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
            rows,
        )

    def session_exists(
        self,
        session_id: str,
        tenant_id: str = "",
        *,
        system_access: SystemAccess | None = None,
    ) -> bool:
        """判断会话是否存在；带 tenant 时同时校验租户归属。

        空租户默认拒绝，仅显式 `SYSTEM_ACCESS` 通道可跨租户探测；
        否则 `list_projection` 等调用会退化为全库可读（跨租户 IDOR）。
        """
        system = resolve_system_access(
            system_access, operation="session_exists", session_id=session_id
        )
        if not tenant_id and not system:
            raise TenantIsolationError(session_id, "session_exists")
        if tenant_id:
            sql = "SELECT 1 FROM sessions WHERE session_id = %s AND tenant_id = %s::uuid"
            params: tuple[Any, ...] = (session_id, tenant_id)
        else:
            sql = "SELECT 1 FROM sessions WHERE session_id = %s"
            params = (session_id,)
        with self._get_conn() as conn:
            row = conn.execute(sql, params).fetchone()
        return row is not None

    def list_projection(
        self,
        table: str,
        session_id: str,
        tenant_id: str = "",
        filters: dict[str, Any] | None = None,
        *,
        system_access: SystemAccess | None = None,
    ) -> list[dict] | None:
        """直接读取投影表；None 表示会话不存在（含跨租户），[] 表示合法空集合。"""
        spec = get_projection_spec(table)
        if not self.session_exists(session_id, tenant_id, system_access=system_access):
            return None
        clauses = ["session_id = %s"]
        params: list[Any] = [session_id]
        for key, value in (filters or {}).items():
            if key not in spec.filters:
                raise ValueError(f"Unsupported projection filter: {key}")
            clauses.append(f"{key} = %s")
            params.append(value)
        # table / order_by / filter 列均来自 PROJECTION_TABLES 白名单。
        sql = f"SELECT * FROM {table} WHERE {' AND '.join(clauses)} ORDER BY {spec.order_by}"  # noqa: S608
        with self._get_conn() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return build_projection_rows(table, [dict(row) for row in rows])

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

    @staticmethod
    def _decrypt_report_content(value: Any) -> dict:
        """report_artifacts.content_json 可能是明文 JSONB 或加密字符串。"""
        if isinstance(value, str):
            decrypted = decrypt_text_field(value, field="report_artifacts.content_json")
            try:
                loaded = json.loads(decrypted or "{}")
            except json.JSONDecodeError:
                return {}
            return loaded if isinstance(loaded, dict) else {}
        return value or {}

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
            content = self._decrypt_report_content(row.get("content_json"))
            artifacts.append(
                {
                    "report_id": row["report_id"],
                    "session_id": row["session_id"],
                    "version": row["version"],
                    "generated_at": row["generated_at"].isoformat()
                    if row.get("generated_at")
                    else None,
                    "content_json": content,
                    "content_markdown": decrypt_text_field(
                        row.get("content_markdown"), field="report_artifacts.content_markdown"
                    )
                    or "",
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
        content = self._decrypt_report_content(row.get("content_json"))
        return {
            "report_id": row["report_id"],
            "session_id": row["session_id"],
            "version": row["version"],
            "generated_at": row["generated_at"].isoformat() if row.get("generated_at") else None,
            "content_json": content,
            "content_markdown": decrypt_text_field(
                row.get("content_markdown"), field="report_artifacts.content_markdown"
            )
            or "",
            "ai_generated": content.get("ai_generated", {}),
            "human_reviewed": content.get("human_reviewed", {}),
            "evidence": content.get("evidence_sources", []),
            "audit_events": content.get("audit_events", []),
            "open_risks": content.get("open_risks", []),
            "eval_summary": content.get("eval_summary", {}),
            "eval_runs": content.get("eval_runs", []),
            "failed_eval_runs": content.get("failed_eval_runs", []),
        }

    @_record_db_operation("load")
    def load(
        self,
        session_id: str,
        tenant_id: str = "",
        *,
        system_access: SystemAccess | None = None,
    ) -> ProjectContext | None:
        """加载会话，不存在或 tenant 不匹配则返回 None。

        生产路径必须显式携带 tenant；`system_access=SYSTEM_ACCESS` 仅供启动补偿、
        审计等无请求上下文的内部通道使用，每次使用都会记录 warning 审计日志。
        """
        system = resolve_system_access(system_access, operation="load", session_id=session_id)
        if not tenant_id and not system:
            raise TenantIsolationError(session_id, "load")
        params: tuple[Any, ...]
        if tenant_id:
            sql = (
                "SELECT context_json, tenant_id::text, version, updated_at FROM sessions "
                "WHERE session_id = %s AND tenant_id = %s::uuid"
            )
            params = (session_id, tenant_id)
        else:
            sql = (
                "SELECT context_json, tenant_id::text, version, updated_at "
                "FROM sessions WHERE session_id = %s"
            )
            params = (session_id,)
        with self._get_conn() as conn:
            row = conn.execute(sql, params).fetchone()
        if not row:
            return None
        ctx = migrate_context(sanitize_persisted_state(row["context_json"]))
        if ctx:
            decrypt_fields_after_load(ctx)
            if row.get("tenant_id"):
                ctx.tenant_id = row["tenant_id"]
            if row.get("updated_at"):
                ctx.updated_at = row["updated_at"]
            ctx._storage_version = int(row.get("version") or 0)
        return ctx

    def archive_audit_events(self, session_id: str, purged_by: str, summary: dict) -> int:
        """Copy audit_events to audit_events_archive + write session_purged event.

        Returns the number of events archived (including the purge event).
        """
        import json
        import uuid

        archived = 0
        with self._get_conn() as conn:
            # Copy existing audit events
            rows = conn.execute(
                "SELECT event_id, actor, event_type, target_type, target_id, "
                "before_hash, after_hash, before_snapshot, after_snapshot, metadata, created_at "
                "FROM audit_events WHERE session_id = %s",
                (session_id,),
            ).fetchall()
            for row in rows:
                conn.execute(
                    "INSERT INTO audit_events_archive "
                    "(archive_id, original_session_id, event_id, actor, event_type, "
                    "target_type, target_id, before_hash, after_hash, before_snapshot, "
                    "after_snapshot, metadata, original_created_at, archived_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()) "
                    "ON CONFLICT (archive_id) DO NOTHING",
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
                        json.dumps(row["before_snapshot"], default=str)
                        if row["before_snapshot"] is not None
                        else None,
                        json.dumps(row["after_snapshot"], default=str)
                        if row["after_snapshot"] is not None
                        else None,
                        json.dumps(row["metadata"], default=str),
                        row["created_at"],
                    ),
                )
                archived += 1

            # Write session_purged event
            conn.execute(
                "INSERT INTO audit_events_archive "
                "(archive_id, original_session_id, event_id, actor, event_type, "
                "target_type, target_id, before_hash, after_hash, before_snapshot, "
                "after_snapshot, metadata, original_created_at, archived_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, NULL, NULL, %s, %s, NOW(), NOW())",
                (
                    f"arch-purged-{uuid.uuid4()}",
                    session_id,
                    f"purge-{uuid.uuid4()}",
                    purged_by,
                    "session_purged",
                    "session",
                    session_id,
                    json.dumps(summary, default=str),
                    json.dumps({"purged_by": purged_by}, default=str),
                ),
            )
            archived += 1
            conn.commit()
        return archived

    def purge_session(
        self,
        session_id: str,
        tenant_id: str,
        purged_by: str,
        summary: dict,
    ) -> int:
        """Archive audit evidence and delete a session in one transaction."""
        import uuid

        archived = 0
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT event_id, actor, event_type, target_type, target_id, "
                "before_hash, after_hash, before_snapshot, after_snapshot, metadata, created_at "
                "FROM audit_events WHERE session_id = %s",
                (session_id,),
            ).fetchall()
            for row in rows:
                conn.execute(
                    "INSERT INTO audit_events_archive "
                    "(archive_id, original_session_id, event_id, actor, event_type, "
                    "target_type, target_id, before_hash, after_hash, before_snapshot, "
                    "after_snapshot, metadata, original_created_at, archived_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()) "
                    "ON CONFLICT (archive_id) DO NOTHING",
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
                        json.dumps(row["before_snapshot"], default=str)
                        if row["before_snapshot"] is not None
                        else None,
                        json.dumps(row["after_snapshot"], default=str)
                        if row["after_snapshot"] is not None
                        else None,
                        json.dumps(row["metadata"], default=str),
                        row["created_at"],
                    ),
                )
                archived += 1
            conn.execute(
                "INSERT INTO audit_events_archive "
                "(archive_id, original_session_id, event_id, actor, event_type, target_type, "
                "target_id, before_snapshot, after_snapshot, metadata, original_created_at, archived_at) "
                "VALUES (%s, %s, %s, %s, 'session_purged', 'session', %s, NULL, %s, %s, NOW(), NOW())",
                (
                    f"arch-purged-{uuid.uuid4()}",
                    session_id,
                    f"purge-{uuid.uuid4()}",
                    purged_by,
                    session_id,
                    json.dumps(summary, default=str),
                    json.dumps({"purged_by": purged_by}, default=str),
                ),
            )
            archived += 1
            # 评估记录是旁路投影数据，不保留跨会话历史，随会话一并回收。
            # 租户谓词防止同名 session_id 的跨租户残留被误删。
            if tenant_id:
                conn.execute(
                    "DELETE FROM gate_evaluation_records WHERE session_id = %s "
                    "AND (tenant_id = %s OR tenant_id IS NULL OR tenant_id = '')",
                    (session_id, tenant_id),
                )
            else:
                conn.execute(
                    "DELETE FROM gate_evaluation_records WHERE session_id = %s", (session_id,)
                )
            if tenant_id:
                cursor = conn.execute(
                    "DELETE FROM sessions WHERE session_id = %s AND tenant_id = %s::uuid",
                    (session_id, tenant_id),
                )
            else:
                cursor = conn.execute("DELETE FROM sessions WHERE session_id = %s", (session_id,))
            if cursor.rowcount != 1:
                raise ValueError(f"Session not found during purge: {session_id}")
            conn.commit()
        return archived

    @_record_db_operation("retention")
    def count_expired_sessions(self, cutoff: datetime) -> int:
        """统计最后更新时间早于留存截止点的会话数。"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM sessions WHERE updated_at < %s", (cutoff,)
            ).fetchone()
        if row is None:
            raise RuntimeError("retention count query returned no row")
        return int(row["n"])

    @_record_db_operation("retention")
    def list_expired_sessions(self, cutoff: datetime, limit: int = 1_000) -> list[dict]:
        """按最旧优先列出留存候选；历史行 tenant_id 可能为 NULL。"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT session_id, tenant_id::text AS tenant_id, current_state, "
                "created_at, updated_at FROM sessions "
                "WHERE updated_at < %s ORDER BY updated_at ASC LIMIT %s",
                (cutoff, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    @_record_db_operation("retention")
    def count_audit_events_before(self, cutoff: datetime) -> dict[str, int]:
        """统计超过留存期的活动审计与归档审计行数，不做任何删除。"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT "
                "(SELECT COUNT(*) FROM audit_events WHERE created_at < %s) AS audit_events, "
                "(SELECT COUNT(*) FROM audit_events_archive "
                " WHERE original_created_at < %s) AS archived_events",
                (cutoff, cutoff),
            ).fetchone()
        if row is None:
            raise RuntimeError("retention audit count query returned no row")
        return {
            "audit_events": int(row["audit_events"]),
            "archived_events": int(row["archived_events"]),
        }

    @_record_db_operation("retention")
    def purge_audit_events_before(self, cutoff: datetime, limit: int = 1_000) -> dict[str, int]:
        """按批删除超过留存期的审计行；两批删除在同一事务内提交。"""
        live_sql = (
            "WITH stale AS ("
            "SELECT event_id FROM audit_events WHERE created_at < %s "
            "ORDER BY created_at ASC LIMIT %s) "
            "DELETE FROM audit_events WHERE event_id IN (SELECT event_id FROM stale)"
        )
        archive_sql = (
            "WITH stale AS ("
            "SELECT archive_id FROM audit_events_archive WHERE original_created_at < %s "
            "ORDER BY original_created_at ASC LIMIT %s) "
            "DELETE FROM audit_events_archive WHERE archive_id IN "
            "(SELECT archive_id FROM stale)"
        )
        with self._get_conn() as conn:
            live_cursor = conn.execute(live_sql, (cutoff, limit))
            archived_cursor = conn.execute(archive_sql, (cutoff, limit))
            conn.commit()
        return {
            "audit_events": max(live_cursor.rowcount, 0),
            "archived_events": max(archived_cursor.rowcount, 0),
        }

    def enqueue_interrupt_resume(self, ctx: ProjectContext, record: Any) -> None:
        """Persist one idempotent resume delivery before invoking LangGraph."""
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO interrupt_resume_outbox (
                    interrupt_id, session_id, tenant_id, action_id, thread_id,
                    checkpoint_ns, resume_payload, status, updated_at
                ) VALUES (%s, %s, %s::uuid, %s, %s, %s, %s, 'pending', NOW())
                ON CONFLICT (action_id) DO UPDATE SET
                    resume_payload = EXCLUDED.resume_payload,
                    updated_at = NOW(),
                    status = CASE
                        WHEN interrupt_resume_outbox.status = 'completed' THEN 'completed'
                        ELSE 'pending'
                    END,
                    last_error = CASE
                        WHEN interrupt_resume_outbox.status = 'completed'
                        THEN interrupt_resume_outbox.last_error ELSE NULL
                    END
                """,
                (
                    record.interrupt_id,
                    ctx.session_id,
                    ctx.tenant_id or None,
                    record.action_id,
                    record.thread_id,
                    record.checkpoint_ns,
                    json.dumps(record.resume_value or {}, default=str),
                ),
            )
            conn.commit()

    def claim_interrupt_resume(self, interrupt_id: str) -> bool:
        """Atomically claim a pending/failed or abandoned resume delivery."""
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                UPDATE interrupt_resume_outbox
                SET status = 'processing', attempts = attempts + 1,
                    claimed_at = NOW(), updated_at = NOW(), last_error = NULL
                WHERE interrupt_id = %s
                  AND (
                    status IN ('pending', 'failed')
                    OR (status = 'processing' AND claimed_at < NOW() - INTERVAL '5 minutes')
                  )
                """,
                (interrupt_id,),
            )
            conn.commit()
            return cursor.rowcount == 1

    def complete_interrupt_resume(self, interrupt_id: str, error: str = "") -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                UPDATE interrupt_resume_outbox
                SET status = %s, completed_at = CASE WHEN %s = '' THEN NOW() ELSE NULL END,
                    last_error = NULLIF(%s, ''), updated_at = NOW()
                WHERE interrupt_id = %s
                """,
                ("failed" if error else "completed", error, error, interrupt_id),
            )
            conn.commit()

    def list_pending_interrupt_resumes(self, limit: int = 100) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT interrupt_id, session_id, tenant_id::text, action_id
                FROM interrupt_resume_outbox
                WHERE status IN ('pending', 'failed')
                   OR (status = 'processing' AND claimed_at < NOW() - INTERVAL '5 minutes')
                ORDER BY updated_at, created_at
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete(
        self, session_id: str, tenant_id: str = "", *, system_access: SystemAccess | None = None
    ) -> bool:
        """Delete a session row. Returns True if a row was deleted."""
        system = resolve_system_access(system_access, operation="delete", session_id=session_id)
        if not tenant_id and not system:
            raise TenantIsolationError(session_id, "delete")
        with self._get_conn() as conn:
            if tenant_id:
                cur = conn.execute(
                    "DELETE FROM sessions WHERE session_id = %s AND tenant_id = %s::uuid",
                    (session_id, tenant_id),
                )
            else:
                cur = conn.execute(
                    "DELETE FROM sessions WHERE session_id = %s",
                    (session_id,),
                )
            conn.commit()
            return cur.rowcount > 0

    @_record_db_operation("list")
    def list_sessions(
        self,
        limit: int = 20,
        tenant_id: str = "",
        *,
        system_access: SystemAccess | None = None,
        offset: int = 0,
    ) -> list[dict]:
        """列出最近的会话（用于前端历史列表）。生产路径必须携带 tenant。

        读取 V008 生成列，避免为列表页解析整份 context_json。
        """
        system = resolve_system_access(system_access, operation="list_sessions", session_id="")
        if not tenant_id and not system:
            raise TenantIsolationError("", "list_sessions")
        columns = (
            "session_id, current_state, created_at, updated_at, "
            "session_name, scenario_name, research_target, domain"
        )
        params: tuple[Any, ...]
        if tenant_id:
            sql = f"""
                SELECT {columns}
                FROM sessions
                WHERE tenant_id = %s::uuid
                ORDER BY updated_at DESC
                LIMIT %s OFFSET %s
            """  # noqa: S608  # column list is a module-level constant
            params = (tenant_id, limit, offset)
        else:
            sql = f"""
                SELECT {columns}
                FROM sessions
                ORDER BY updated_at DESC
                LIMIT %s OFFSET %s
            """  # noqa: S608  # column list is a module-level constant
            params = (limit, offset)
        with self._get_conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # ── Tenant maintenance ──────────────────────────────────────────────────

    @_record_db_operation("backfill_tenant")
    def backfill_orphan_sessions(
        self,
        tenant_id: str,
        session_ids: list[str] | None = None,
        *,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """为历史上 tenant_id 为 NULL 的会话回填租户归属（幂等）。

        早于多租户模型创建的会话没有租户归属，默认租户作用域查询不可见，
        也不进入治理统计。本方法提供受控回填通道：

        - 默认 dry_run，只统计匹配行数，不写库；
        - 仅更新 tenant_id IS NULL 的行，已有归属的行永不覆盖，可重复执行；
        - human_actions / interrupt_resume_outbox / gate_evaluation_records
          按 session_id 联表回填，同样只填 NULL 行；所有更新在同一事务内提交；
        - tenant 不存在时抛 ValueError，避免把会话挂到无效租户。
        """
        with self._get_conn() as conn:
            tenant_row = conn.execute(
                "SELECT 1 AS ok FROM tenants WHERE tenant_id = %s::uuid", (tenant_id,)
            ).fetchone()
            if tenant_row is None:
                raise ValueError(f"Tenant not found: {tenant_id}")

            if session_ids:
                rows = conn.execute(
                    "SELECT session_id FROM sessions "
                    "WHERE tenant_id IS NULL AND session_id = ANY(%s)",
                    (list(session_ids),),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT session_id FROM sessions WHERE tenant_id IS NULL"
                ).fetchall()
            target_ids = [row["session_id"] for row in rows]

            result: dict[str, Any] = {
                "tenant_id": tenant_id,
                "dry_run": dry_run,
                "sessions_matched": len(target_ids),
                "sessions_updated": 0,
                "human_actions_updated": 0,
                "interrupt_resume_outbox_updated": 0,
                "gate_evaluation_records_updated": 0,
            }
            if dry_run or not target_ids:
                return result

            session_cursor = conn.execute(
                "UPDATE sessions SET tenant_id = %s::uuid "
                "WHERE session_id = ANY(%s) AND tenant_id IS NULL",
                (tenant_id, target_ids),
            )
            # 必须先更新 sessions，再按 JOIN 回填依赖表——同事务内 s.tenant_id 已是新归属。
            action_cursor = conn.execute(
                "UPDATE human_actions AS h SET tenant_id = s.tenant_id "
                "FROM sessions AS s "
                "WHERE h.session_id = s.session_id AND h.tenant_id IS NULL "
                "AND s.session_id = ANY(%s)",
                (target_ids,),
            )
            outbox_cursor = conn.execute(
                "UPDATE interrupt_resume_outbox AS o SET tenant_id = s.tenant_id "
                "FROM sessions AS s "
                "WHERE o.session_id = s.session_id AND o.tenant_id IS NULL "
                "AND s.session_id = ANY(%s)",
                (target_ids,),
            )
            gate_cursor = conn.execute(
                "UPDATE gate_evaluation_records AS g SET tenant_id = s.tenant_id::text "
                "FROM sessions AS s "
                "WHERE g.session_id = s.session_id AND g.tenant_id IS NULL "
                "AND s.session_id = ANY(%s)",
                (target_ids,),
            )
            conn.commit()
            result["sessions_updated"] = session_cursor.rowcount
            result["human_actions_updated"] = action_cursor.rowcount
            result["interrupt_resume_outbox_updated"] = outbox_cursor.rowcount
            result["gate_evaluation_records_updated"] = gate_cursor.rowcount
            return result

    def log_event(
        self,
        session_id: str,
        event_type: str,
        stage: int | None,
        payload: dict,
    ) -> None:
        """记录会话事件（用于审计和调试）。

        tenant_id 通过 INSERT ... SELECT 从 sessions 回填，避免修改所有调用点。
        """
        sql = """
            INSERT INTO session_events (session_id, event_type, stage, payload, tenant_id)
            SELECT session_id, %s, %s, %s, tenant_id
            FROM sessions
            WHERE session_id = %s
        """
        with self._get_conn() as conn:
            conn.execute(
                sql,
                (event_type, stage, json.dumps(payload, default=str), session_id),
            )
            conn.commit()

    # ── Auth methods ──────────────────────────────────────────────────────────

    def create_tenant(self, name: str) -> dict:
        """Create a new tenant, return tenant_id."""
        sql = "INSERT INTO tenants (name) VALUES (%s) RETURNING tenant_id::text, name, created_at"
        with self._get_conn() as conn:
            row = conn.execute(sql, (name,)).fetchone()
            conn.commit()
        return dict(cast(dict[str, Any], row))

    def create_user(
        self, tenant_id: str, email: str, password_hash: str, role: str = "viewer"
    ) -> dict:
        """Create a user. Raises on duplicate email."""
        sql = """
            INSERT INTO users (tenant_id, email, password_hash, role)
            VALUES (%s::uuid, %s, %s, %s)
            RETURNING user_id::text, tenant_id::text, email, role, created_at
        """
        with self._get_conn() as conn:
            row = conn.execute(sql, (tenant_id, email, password_hash, role)).fetchone()
            conn.commit()
        return dict(cast(dict[str, Any], row))

    def get_user_by_email(self, email: str) -> dict | None:
        """Lookup user by email for login."""
        sql = "SELECT user_id::text, tenant_id::text, email, password_hash, role FROM users WHERE email = %s"
        with self._get_conn() as conn:
            row = conn.execute(sql, (email,)).fetchone()
        return dict(row) if row else None

    def count_users(self) -> int:
        """Return total number of users (for first-admin bootstrap)."""
        with self._get_conn() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
            return row["n"] if row else 0

    def list_users_by_tenant(self, tenant_id: str) -> list[dict]:
        """List all users belonging to a tenant."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT user_id, tenant_id, email, role, created_at "
                "FROM users WHERE tenant_id = %s ORDER BY created_at",
                (tenant_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def update_user_role(self, user_id: str, tenant_id: str, new_role: str) -> dict | None:
        """Update role for a user within the same tenant. Returns updated user or None."""
        with self._get_conn() as conn:
            row = conn.execute(
                "UPDATE users SET role = %s "
                "WHERE user_id = %s AND tenant_id = %s "
                "RETURNING user_id, tenant_id::text, email, role",
                (new_role, user_id, tenant_id),
            ).fetchone()
            conn.commit()
            return dict(row) if row else None

    def get_user_by_id(self, user_id: str) -> dict | None:
        """Lookup the current member record for refresh-token role revalidation."""
        sql = (
            "SELECT user_id::text, tenant_id::text, email, role FROM users WHERE user_id = %s::uuid"
        )
        with self._get_conn() as conn:
            row = conn.execute(sql, (user_id,)).fetchone()
        return dict(row) if row else None

    def create_invitation(
        self,
        *,
        tenant_id: str,
        email: str,
        role: str,
        token_hash: str,
        invited_by: str,
        expires_at: datetime,
    ) -> dict:
        sql = """
            INSERT INTO workspace_invitations (
                tenant_id, email, role, token_hash, status, invited_by, expires_at
            ) VALUES (%s::uuid, %s, %s, %s, 'pending', %s, %s)
            RETURNING invitation_id::text, tenant_id::text, email, role, status,
                      invited_by::text, expires_at, accepted_at, accepted_user_id::text, created_at
        """
        with self._get_conn() as conn:
            row = conn.execute(
                sql,
                (
                    tenant_id,
                    email,
                    role,
                    token_hash,
                    invited_by or None,
                    expires_at,
                ),
            ).fetchone()
            conn.commit()
        return dict(cast(dict[str, Any], row))

    def list_invitations_by_tenant(self, tenant_id: str) -> list[dict]:
        sql = """
            SELECT invitation_id::text, tenant_id::text, email, role, status,
                   invited_by::text, expires_at, accepted_at, accepted_user_id::text, created_at
            FROM workspace_invitations
            WHERE tenant_id = %s::uuid
            ORDER BY created_at DESC
        """
        with self._get_conn() as conn:
            rows = conn.execute(sql, (tenant_id,)).fetchall()
        return [dict(row) for row in rows]

    def get_invitation_by_token_hash(self, token_hash: str) -> dict | None:
        sql = """
            SELECT invitation_id::text, tenant_id::text, email, role, status,
                   invited_by::text, expires_at, accepted_at, accepted_user_id::text, created_at
            FROM workspace_invitations
            WHERE token_hash = %s
        """
        with self._get_conn() as conn:
            row = conn.execute(sql, (token_hash,)).fetchone()
        return dict(row) if row else None

    def accept_invitation(
        self,
        *,
        invitation_id: str,
        password_hash: str,
        accepted_at: datetime,
    ) -> dict | None:
        """Atomically create the invited user and mark the invitation accepted."""
        with self._get_conn() as conn:
            invitation = conn.execute(
                "SELECT invitation_id::text, tenant_id::text, email, role, status "
                "FROM workspace_invitations WHERE invitation_id = %s::uuid FOR UPDATE",
                (invitation_id,),
            ).fetchone()
            if invitation is None or invitation["status"] != "pending":
                return None
            user_row = conn.execute(
                "INSERT INTO users (tenant_id, email, password_hash, role) "
                "VALUES (%s::uuid, %s, %s, %s) "
                "RETURNING user_id::text, tenant_id::text, email, role",
                (
                    invitation["tenant_id"],
                    invitation["email"],
                    password_hash,
                    invitation["role"],
                ),
            ).fetchone()
            if user_row is None:
                raise ValueError("Failed to create invited user")
            updated = conn.execute(
                "UPDATE workspace_invitations SET status = 'accepted', accepted_at = %s, "
                "accepted_user_id = %s::uuid "
                "WHERE invitation_id = %s::uuid AND status = 'pending'",
                (accepted_at, user_row["user_id"], invitation_id),
            )
            if updated.rowcount == 0:
                raise ValueError("Invitation was accepted by another request")
            conn.commit()
        return dict(user_row)

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
        import uuid

        # 完整 UUID：评估量增长后 8 位前缀存在主键碰撞风险。
        record_id = str(uuid.uuid4())
        sql = """
            INSERT INTO gate_evaluation_records (
                record_id, session_id, tenant_id, stage_id, risk_tier, passed,
                blocking_rule_ids, rule_versions, evaluated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """
        with self._get_conn() as conn:
            conn.execute(
                sql,
                (
                    record_id,
                    session_id,
                    tenant_id or None,
                    stage_id,
                    risk_tier,
                    passed,
                    json.dumps(blocking_rule_ids, default=str),
                    json.dumps(rule_versions, default=str),
                ),
            )
            conn.commit()

    @_record_db_operation("governance")
    def gate_trends(self, tenant_id: str, weeks: int = 8) -> list[dict]:
        """按周聚合真实业务会话的门禁趋势；空 tenant_id 不跨租户查询。"""
        if not tenant_id:
            return []
        sql = """
            SELECT date_trunc('week', ger.evaluated_at)::date::text AS week,
                   ger.passed,
                   ger.blocking_rule_ids
            FROM gate_evaluation_records AS ger
            JOIN sessions AS s ON s.session_id = ger.session_id
            WHERE ger.tenant_id = %s
              AND s.tenant_id = %s::uuid
              AND COALESCE(s.data_classification, 'business_internal')
                  <> 'public_demo'
              AND NULLIF(s.selected_scenario_id, '') IS NULL
              AND ger.evaluated_at >= NOW() - (%s || ' weeks')::INTERVAL
            ORDER BY week DESC
        """
        with self._get_conn() as conn:
            rows = conn.execute(sql, (tenant_id, tenant_id, str(weeks))).fetchall()
        return _aggregate_gate_trends(rows)

    @_record_db_operation("governance")
    def governance_overview(self, tenant_id: str) -> dict:
        """租户内真实业务治理总览；内置场景演示会话不参与聚合。"""
        zero = {
            "sessions_total": 0,
            "state_distribution": {},
            "risk_tier_distribution": {},
            "open_safety_findings": 0,
            "pending_actions": 0,
            "reports_exported": 0,
            "excluded_demo_sessions": 0,
        }
        if not tenant_id:
            return zero
        with self._get_conn() as conn:
            state_rows = conn.execute(_GOV_STATE_SQL, (tenant_id,)).fetchall()
            eval_rows = conn.execute(_GOV_EVAL_SQL, (tenant_id, tenant_id)).fetchall()
            finding_row = conn.execute(_GOV_FINDING_SQL, (tenant_id,)).fetchone()
            action_row = conn.execute(_GOV_ACTION_SQL, (tenant_id,)).fetchone()
            report_row = conn.execute(_GOV_REPORT_SQL, (tenant_id,)).fetchone()
            demo_row = conn.execute(_GOV_DEMO_SQL, (tenant_id,)).fetchone()
        overview = _aggregate_governance_overview(
            state_rows,
            eval_rows,
            {
                "open_safety_findings": finding_row["n"] if finding_row else 0,
                "pending_actions": action_row["n"] if action_row else 0,
                "reports_exported": report_row["n"] if report_row else 0,
            },
        )
        overview["excluded_demo_sessions"] = demo_row["n"] if demo_row else 0
        return overview

    @_record_db_operation("governance")
    def actions_backlog(self, tenant_id: str, limit: int = 50) -> list[dict]:
        """真实业务会话的待处理动作；空 tenant_id 返回空列表。"""
        if not tenant_id:
            return []
        with self._get_conn() as conn:
            rows = conn.execute(_GOV_BACKLOG_SQL, (tenant_id,)).fetchall()
        return _aggregate_actions_backlog(rows, limit)

    @_record_db_operation("governance")
    def governance_metrics_all_tenants(self) -> dict:
        """跨租户聚合的 Prometheus 指标数据（全局监控视角，2026-09-01 修复③）。

        与 per-tenant 的 governance_overview 不同，本方法无租户过滤——
        Prometheus 业务 Gauge 是进程级全局指标，刷新点（lifespan 启动）无
        请求上下文，取全部租户聚合。
        """
        state_distribution: dict[str, int] = {}
        pending_by_risk: dict[str, int] = {}
        with self._get_conn() as conn:
            state_rows = conn.execute(_GOV_METRICS_STATE_SQL).fetchall()
            risk_rows = conn.execute(_GOV_METRICS_RISK_SQL).fetchall()
        for row in state_rows:
            state_distribution[row["current_state"]] = row["n"]
        for row in risk_rows:
            pending_by_risk[row["risk_level"] or "unknown"] = row["n"]
        return {
            "state_distribution": state_distribution,
            "pending_actions_by_risk": pending_by_risk,
        }


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
    state_rows: list[dict],
    eval_rows: list[dict],
    counts: dict[str, int],
) -> dict:
    """Shared governance-overview aggregation.

    `counts` carries the projection-table aggregates (safety findings, pending
    actions, exported reports) so this helper never parses `context_json`.
    """
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

    return {
        "sessions_total": sessions_total,
        "state_distribution": state_distribution,
        "risk_tier_distribution": risk_tier_distribution,
        "open_safety_findings": counts.get("open_safety_findings", 0),
        "pending_actions": counts.get("pending_actions", 0),
        "reports_exported": counts.get("reports_exported", 0),
    }


def _isoformat(value: Any) -> str:
    """Normalize timestamps from JSON strings or DB datetimes to ISO strings."""
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _aggregate_actions_backlog(rows: list[dict], limit: int) -> list[dict]:
    """Shared actions-backlog aggregation."""
    risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    actions: list[dict] = [
        {
            "session_id": row["session_id"],
            "action_id": row.get("action_id"),
            "title": row.get("title"),
            "risk_level": row.get("risk_level", "medium"),
            "stage_id": row.get("stage_id"),
            "created_at": _isoformat(row.get("created_at")),
        }
        for row in rows
    ]
    actions.sort(key=lambda a: (risk_order.get(a["risk_level"], 4), a["created_at"]))
    return actions[:limit]
