"""Backfill the historical plaintext ``goal`` field in ``sessions.context_json``.

Usage:
    uv run python scripts/encrypt_legacy_goal.py --verify
    uv run python scripts/encrypt_legacy_goal.py --apply
    uv run python scripts/encrypt_legacy_goal.py --decrypt --apply --allow-plaintext

Default is dry-run: the sweep reports what would change and writes nothing.
``--verify`` only checks that existing ``enc:v1:`` goal ciphertext is
decryptable with the configured DATA_ENCRYPTION_KEY.
"""

from __future__ import annotations

import argparse
import json

from storage.session_store import session_store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Encrypt or verify legacy plaintext goal fields.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际写库；缺省为 dry-run，只统计不修改",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="只校验已有 enc:v1: goal 是否可用当前密钥解密，不写库",
    )
    parser.add_argument(
        "--decrypt",
        action="store_true",
        help="回滚辅助：把 goal 密文还原为明文（必须同时提供 --allow-plaintext）",
    )
    parser.add_argument(
        "--allow-plaintext",
        action="store_true",
        help="显式确认 decrypt 模式会写回明文",
    )
    parser.add_argument(
        "--session-id",
        action="append",
        dest="session_ids",
        default=None,
        help="只处理指定会话（可重复）；缺省处理全部会话",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="每批读取行数（默认 100）",
    )
    args = parser.parse_args(argv)

    if args.verify and args.decrypt:
        print(
            json.dumps(
                {"error": "--verify and --decrypt are mutually exclusive"}, ensure_ascii=False
            )
        )
        return 2
    if args.decrypt and not args.allow_plaintext:
        print(
            json.dumps(
                {
                    "error": (
                        "decrypt mode writes plaintext; pass --allow-plaintext explicitly "
                        "and only use it before rolling back to a pre-1.7 application."
                    )
                },
                ensure_ascii=False,
            )
        )
        return 2

    method = getattr(session_store, "backfill_goal_encryption", None)
    if method is None:
        print(
            json.dumps(
                {"error": "Active storage backend does not support goal encryption backfill"},
                ensure_ascii=False,
            )
        )
        return 2

    try:
        result = method(
            dry_run=not args.apply,
            verify_only=args.verify,
            decrypt=args.decrypt,
            session_ids=args.session_ids,
            batch_size=args.batch_size,
        )
    except Exception as exc:  # 配置/数据库/解密错误：输出结构化错误而不是 traceback
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
