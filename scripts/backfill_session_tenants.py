"""Backfill tenant ownership for historical sessions whose tenant_id is NULL.

Usage:
    uv run python scripts/backfill_session_tenants.py --tenant-id <uuid>
    uv run python scripts/backfill_session_tenants.py --tenant-id <uuid> --apply
    uv run python scripts/backfill_session_tenants.py --tenant-id <uuid> --session-id <id> --apply

Dry-run by default: reports how many orphan sessions match, writes nothing.
"""

from __future__ import annotations

import argparse
import json

from storage.backends.postgres import PostgresSessionStore
from storage.session_store import session_store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill tenant_id for orphan sessions.")
    parser.add_argument("--tenant-id", required=True, help="回填目标租户 UUID")
    parser.add_argument(
        "--session-id",
        action="append",
        dest="session_ids",
        default=None,
        help="只回填指定会话（可重复）；缺省处理全部 tenant_id 为 NULL 的会话",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际写库；缺省为 dry-run，只统计不修改",
    )
    args = parser.parse_args(argv)

    if not isinstance(session_store, PostgresSessionStore):
        print(
            json.dumps(
                {"error": "STORAGE_BACKEND must be postgres for tenant backfill"},
                ensure_ascii=False,
            )
        )
        return 2

    try:
        result = session_store.backfill_orphan_sessions(
            args.tenant_id,
            args.session_ids,
            dry_run=not args.apply,
        )
    except Exception as exc:  # 租户不存在或数据库不可达：输出结构化错误而不是 traceback
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
