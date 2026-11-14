"""Controlled backfill for historical audit/event payloads (P0 T02/T09).

Usage:
    uv run python scripts/redact_legacy_audit_payloads.py
    uv run python scripts/redact_legacy_audit_payloads.py --apply
    uv run python scripts/redact_legacy_audit_payloads.py --apply \
        --tables audit_events_archive --report .upgrade/logs/audit-redaction.json

Dry-run by default: reports how many rows would change, writes nothing.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from storage.audit_redaction import DEFAULT_TABLES, redact_legacy_audit_payloads
from storage.session_store import session_store


def _parse_tables(values: list[str] | None) -> tuple[str, ...]:
    if not values:
        return DEFAULT_TABLES
    allowed = set(DEFAULT_TABLES)
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise ValueError(f"Unsupported table(s): {', '.join(unknown)}")
    return tuple(values)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Redact historical audit/event payloads in controlled batches."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际写库；缺省为 dry-run，只统计将修改的行",
    )
    parser.add_argument("--batch-size", type=int, default=200, help="每批行数（默认 200）")
    parser.add_argument("--max-batches", type=int, default=None, help="每个表最多处理批次数")
    parser.add_argument(
        "--tables",
        action="append",
        choices=list(DEFAULT_TABLES),
        default=None,
        help="只处理指定表（可重复）；缺省处理 audit_events / audit_events_archive / session_events",
    )
    parser.add_argument("--report", default=None, help="可选：将结构化报告写入指定 JSON 路径")
    args = parser.parse_args(argv)

    try:
        report = redact_legacy_audit_payloads(
            session_store,
            dry_run=not args.apply,
            batch_size=args.batch_size,
            max_batches=args.max_batches,
            tables=_parse_tables(args.tables),
        )
    except Exception as exc:  # 数据库不可达或参数错误：输出结构化错误而不是 traceback
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1

    if args.report:
        path = Path(args.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if report.get("malformed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
