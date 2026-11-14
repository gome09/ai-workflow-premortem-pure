"""Remove legacy context-cache keys after the v2 namespace switch.

Only keys under this application's ``session:ctx:`` namespace that are not
already ``session:ctx:v2:`` are considered. Never flushes the whole database.

Usage:
    uv run python scripts/purge_legacy_context_cache.py
    uv run python scripts/purge_legacy_context_cache.py --apply
"""

from __future__ import annotations

import argparse
import json

from core.config import settings
from storage.cache_keys import CACHE_KEY_PREFIX, LEGACY_CACHE_KEY_PREFIX


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Delete pre-v2 context cache keys.")
    parser.add_argument("--apply", action="store_true", help="实际删除；缺省只统计")
    parser.add_argument("--batch-size", type=int, default=200, help="SCAN 每批数量")
    args = parser.parse_args(argv)

    if settings.storage_backend == "sqlite":
        print(json.dumps({"skipped": "sqlite backend uses in-process MemoryCache"}))
        return 0

    import redis

    client = redis.from_url(settings.redis_url, decode_responses=True)
    scanned = 0
    legacy = 0
    deleted = 0
    prefix = f"{LEGACY_CACHE_KEY_PREFIX}*"
    try:
        for key in client.scan_iter(match=prefix, count=args.batch_size):
            scanned += 1
            if key.startswith(f"{CACHE_KEY_PREFIX}:"):
                continue
            legacy += 1
            if args.apply:
                deleted += int(client.delete(key))
    except redis.RedisError as exc:
        print(json.dumps({"error": type(exc).__name__}, ensure_ascii=False))
        return 1

    print(
        json.dumps(
            {
                "dry_run": not args.apply,
                "scanned": scanned,
                "legacy": legacy,
                "deleted": deleted,
                "new_prefix": CACHE_KEY_PREFIX,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
