"""Controlled backfill for historical audit/event payloads (T02/T09).

The backfill is intentionally conservative:
- active sessions use their current ``data_classification``;
- archived/event rows keep readable payloads only when the parent session still
  exists and is ``public_demo``;
- orphaned archive rows and unknown classifications are redacted.

Rows are processed in keyset batches; each batch is committed independently so
an interrupted run can resume. Malformed JSON is reported and never rewritten.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal

from core.data_protection import redact_payload, sanitize_purge_summary

BACKFILL_VERSION = "p0-2026-11-13"
BACKFILL_MARKER = "_redaction_backfill"
DEFAULT_BATCH_SIZE = 200

TableName = Literal["audit_events", "audit_events_archive", "session_events"]
DEFAULT_TABLES: tuple[TableName, ...] = (
    "audit_events",
    "audit_events_archive",
    "session_events",
)


def _loads(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    return json.loads(raw)


def _dumps(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=False)


def _is_marked(metadata: Any) -> bool:
    return isinstance(metadata, dict) and BACKFILL_MARKER in metadata


def _marker(batch: int) -> dict[str, Any]:
    return {
        "version": BACKFILL_VERSION,
        "at": datetime.now(UTC).isoformat(),
        "batch": batch,
    }


def _redact_audit_row(
    *,
    classification: str,
    event_type: str,
    before: Any,
    after: Any,
    metadata: Any,
    batch: int,
) -> tuple[Any, Any, Any] | None:
    """Return redacted (before, after, metadata) or None when unchanged."""
    original = (before, after, metadata)
    if event_type == "session_purged":
        if isinstance(after, dict):
            after = sanitize_purge_summary(after)
        metadata = redact_payload(metadata or {}, classification)
    else:
        before = redact_payload(before, classification) if before is not None else None
        after = redact_payload(after, classification) if after is not None else None
        metadata = redact_payload(metadata or {}, classification)

    if not isinstance(metadata, dict):
        metadata = {"value": metadata}
    if original == (before, after, metadata):
        return None
    metadata = dict(metadata)
    metadata[BACKFILL_MARKER] = _marker(batch)
    return before, after, metadata


def _redact_session_event(
    *, classification: str, payload: Any, batch: int
) -> dict[str, Any] | None:
    original = payload
    redacted = redact_payload(payload, classification)
    if not isinstance(redacted, dict):
        redacted = {"value": redacted}
    if original == redacted:
        return None
    redacted[BACKFILL_MARKER] = _marker(batch)
    return redacted


def _report(
    *,
    dry_run: bool,
    counts: dict[str, dict[str, int]],
    malformed: list[dict[str, Any]],
    batches: int,
) -> dict[str, Any]:
    return {
        "backfill_version": BACKFILL_VERSION,
        "dry_run": dry_run,
        "tables": counts,
        "malformed": malformed,
        "batches": batches,
    }


def _new_counts() -> dict[str, dict[str, int]]:
    return {table: {"scanned": 0, "changed": 0} for table in DEFAULT_TABLES}


def _process_sqlite(
    store: Any,
    *,
    table: TableName,
    dry_run: bool,
    batch_size: int,
    max_batches: int | None,
) -> tuple[dict[str, int], list[dict[str, Any]], int]:
    counts = {"scanned": 0, "changed": 0}
    malformed: list[dict[str, Any]] = []
    batches = 0
    last_id: Any = 0 if table == "session_events" else ""
    while True:
        if max_batches is not None and batches >= max_batches:
            break
        with store._get_conn() as conn:  # noqa: SLF001 - storage-internal backfill
            if table == "audit_events":
                rows = conn.execute(
                    "SELECT a.event_id, a.event_type, a.before_snapshot, a.after_snapshot, "
                    "a.metadata, COALESCE(json_extract(s.context_json, "
                    "'$.data_classification'), 'business_internal') AS data_classification "
                    "FROM audit_events AS a "
                    "LEFT JOIN sessions AS s ON s.session_id = a.session_id "
                    "WHERE a.event_id > ? ORDER BY a.event_id LIMIT ?",
                    (last_id, batch_size),
                ).fetchall()
            elif table == "audit_events_archive":
                rows = conn.execute(
                    "SELECT a.archive_id, a.event_type, a.before_snapshot, a.after_snapshot, "
                    "a.metadata, COALESCE(json_extract(s.context_json, "
                    "'$.data_classification'), 'business_internal') AS data_classification "
                    "FROM audit_events_archive AS a "
                    "LEFT JOIN sessions AS s ON s.session_id = a.original_session_id "
                    "WHERE a.archive_id > ? ORDER BY a.archive_id LIMIT ?",
                    (last_id, batch_size),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT e.event_id, e.payload, "
                    "COALESCE(json_extract(s.context_json, '$.data_classification'), "
                    "'business_internal') AS data_classification "
                    "FROM session_events AS e "
                    "LEFT JOIN sessions AS s ON s.session_id = e.session_id "
                    "WHERE e.event_id > ? ORDER BY e.event_id LIMIT ?",
                    (last_id, batch_size),
                ).fetchall()
            if not rows:
                break
            batches += 1
            updates: list[tuple[Any, ...]] = []
            for row in rows:
                counts["scanned"] += 1
                last_id = (
                    row["event_id"]
                    if table == "session_events"
                    else row["event_id" if table == "audit_events" else "archive_id"]
                )
                try:
                    if table == "session_events":
                        payload = _loads(row["payload"])
                        if _is_marked(payload):
                            continue
                        new_payload = _redact_session_event(
                            classification=row["data_classification"],
                            payload=payload or {},
                            batch=batches,
                        )
                        if new_payload is not None:
                            updates.append((_dumps(new_payload), row["event_id"]))
                    else:
                        before = _loads(row["before_snapshot"])
                        after = _loads(row["after_snapshot"])
                        metadata = _loads(row["metadata"]) or {}
                        if _is_marked(metadata):
                            continue
                        redacted = _redact_audit_row(
                            classification=row["data_classification"],
                            event_type=row["event_type"],
                            before=before,
                            after=after,
                            metadata=metadata,
                            batch=batches,
                        )
                        if redacted is not None:
                            new_before, new_after, new_metadata = redacted
                            updates.append(
                                (
                                    _dumps(new_before) if new_before is not None else None,
                                    _dumps(new_after) if new_after is not None else None,
                                    _dumps(new_metadata),
                                    row["event_id"]
                                    if table == "audit_events"
                                    else row["archive_id"],
                                )
                            )
                except (TypeError, ValueError) as exc:
                    malformed.append(
                        {
                            "table": table,
                            "id": str(
                                row["event_id"]
                                if table != "audit_events_archive"
                                else row["archive_id"]
                            ),
                            "error": type(exc).__name__,
                        }
                    )
            counts["changed"] += len(updates)
            if updates and not dry_run:
                if table == "session_events":
                    conn.executemany(
                        "UPDATE session_events SET payload = ? WHERE event_id = ?", updates
                    )
                elif table == "audit_events":
                    conn.executemany(
                        "UPDATE audit_events SET before_snapshot = ?, after_snapshot = ?, "
                        "metadata = ? WHERE event_id = ?",
                        updates,
                    )
                else:
                    conn.executemany(
                        "UPDATE audit_events_archive SET before_snapshot = ?, after_snapshot = ?, "
                        "metadata = ? WHERE archive_id = ?",
                        updates,
                    )
                conn.commit()
        if len(rows) < batch_size:
            break
    return counts, malformed, batches


def _process_postgres(
    store: Any,
    *,
    table: TableName,
    dry_run: bool,
    batch_size: int,
    max_batches: int | None,
) -> tuple[dict[str, int], list[dict[str, Any]], int]:
    counts = {"scanned": 0, "changed": 0}
    malformed: list[dict[str, Any]] = []
    batches = 0
    last_id: Any = 0 if table == "session_events" else ""
    while True:
        if max_batches is not None and batches >= max_batches:
            break
        with store._get_conn() as conn:  # noqa: SLF001 - storage-internal backfill
            if table == "audit_events":
                rows = conn.execute(
                    "SELECT a.event_id, a.event_type, a.before_snapshot::text AS before_snapshot, "
                    "a.after_snapshot::text AS after_snapshot, a.metadata::text AS metadata, "
                    "COALESCE(s.data_classification, 'business_internal') AS data_classification "
                    "FROM audit_events AS a "
                    "LEFT JOIN sessions AS s ON s.session_id = a.session_id "
                    "WHERE a.event_id > %s ORDER BY a.event_id LIMIT %s",
                    (last_id, batch_size),
                ).fetchall()
            elif table == "audit_events_archive":
                rows = conn.execute(
                    "SELECT a.archive_id, a.event_type, a.before_snapshot::text AS before_snapshot, "
                    "a.after_snapshot::text AS after_snapshot, a.metadata::text AS metadata, "
                    "COALESCE(s.data_classification, 'business_internal') AS data_classification "
                    "FROM audit_events_archive AS a "
                    "LEFT JOIN sessions AS s ON s.session_id = a.original_session_id "
                    "WHERE a.archive_id > %s ORDER BY a.archive_id LIMIT %s",
                    (last_id, batch_size),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT e.event_id, e.payload::text AS payload, "
                    "COALESCE(s.data_classification, 'business_internal') AS data_classification "
                    "FROM session_events AS e "
                    "LEFT JOIN sessions AS s ON s.session_id = e.session_id "
                    "WHERE e.event_id > %s ORDER BY e.event_id LIMIT %s",
                    (last_id, batch_size),
                ).fetchall()
            if not rows:
                break
            batches += 1
            updates: list[tuple[Any, ...]] = []
            for row in rows:
                counts["scanned"] += 1
                last_id = (
                    row["event_id"]
                    if table == "session_events"
                    else row["event_id" if table == "audit_events" else "archive_id"]
                )
                try:
                    if table == "session_events":
                        payload = _loads(row["payload"])
                        if _is_marked(payload):
                            continue
                        new_payload = _redact_session_event(
                            classification=row["data_classification"],
                            payload=payload or {},
                            batch=batches,
                        )
                        if new_payload is not None:
                            updates.append((_dumps(new_payload), row["event_id"]))
                    else:
                        before = _loads(row["before_snapshot"])
                        after = _loads(row["after_snapshot"])
                        metadata = _loads(row["metadata"]) or {}
                        if _is_marked(metadata):
                            continue
                        redacted = _redact_audit_row(
                            classification=row["data_classification"],
                            event_type=row["event_type"],
                            before=before,
                            after=after,
                            metadata=metadata,
                            batch=batches,
                        )
                        if redacted is not None:
                            new_before, new_after, new_metadata = redacted
                            updates.append(
                                (
                                    _dumps(new_before) if new_before is not None else None,
                                    _dumps(new_after) if new_after is not None else None,
                                    _dumps(new_metadata),
                                    row["event_id"]
                                    if table == "audit_events"
                                    else row["archive_id"],
                                )
                            )
                except (TypeError, ValueError) as exc:
                    malformed.append(
                        {
                            "table": table,
                            "id": str(
                                row["event_id"]
                                if table != "audit_events_archive"
                                else row["archive_id"]
                            ),
                            "error": type(exc).__name__,
                        }
                    )
            counts["changed"] += len(updates)
            if updates and not dry_run:
                if table == "session_events":
                    sql = "UPDATE session_events SET payload = %s::jsonb WHERE event_id = %s"
                elif table == "audit_events":
                    sql = (
                        "UPDATE audit_events SET before_snapshot = %s::jsonb, "
                        "after_snapshot = %s::jsonb, metadata = %s::jsonb WHERE event_id = %s"
                    )
                else:
                    sql = (
                        "UPDATE audit_events_archive SET before_snapshot = %s::jsonb, "
                        "after_snapshot = %s::jsonb, metadata = %s::jsonb WHERE archive_id = %s"
                    )
                with conn.cursor() as cur:
                    cur.executemany(sql, updates)
                conn.commit()
        if len(rows) < batch_size:
            break
    return counts, malformed, batches


def redact_legacy_audit_payloads(
    store: Any,
    *,
    dry_run: bool = True,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_batches: int | None = None,
    tables: tuple[TableName, ...] = DEFAULT_TABLES,
) -> dict[str, Any]:
    """Redact historical audit/event payloads in batches.

    Returns a report with counts and malformed row identifiers; never includes
    original payload content.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    if max_batches is not None and max_batches < 1:
        raise ValueError("max_batches must be >= 1")

    backend = "postgres" if store.__class__.__name__ == "PostgresSessionStore" else "sqlite"
    processor = _process_postgres if backend == "postgres" else _process_sqlite
    counts = _new_counts()
    malformed: list[dict[str, Any]] = []
    batches = 0
    for table in tables:
        table_counts, table_malformed, table_batches = processor(
            store,
            table=table,
            dry_run=dry_run,
            batch_size=batch_size,
            max_batches=max_batches,
        )
        counts[table] = table_counts
        malformed.extend(table_malformed)
        batches += table_batches
    return _report(dry_run=dry_run, counts=counts, malformed=malformed, batches=batches)
