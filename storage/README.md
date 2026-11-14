# Storage Layer

## Migration Mechanism

The current database schema migration mechanism is **Alembic**.

### Production startup path

1. `api/main.py` initializes the session store in the `lifespan` context manager.
2. `storage/backends/postgres.py::PostgresSessionStore.initialize()` runs `alembic upgrade head`.
3. Alembic migrations are under `alembic/versions/` (currently V001 → V014).
   V006 adds the LangGraph PostgreSQL checkpoint schema; V007 adds the durable
   interrupt-resume outbox; V008 adds `sessions.version` (optimistic locking),
   JSONB generated columns, tenant indexes and `human_actions.tenant_id`;
   V009 adds `sessions.projection_state` (save() differential sync state) and
   `eval_runs.pass_criteria` / `llm_judge_suggestion`; V010 adds
   `sessions.context_digest` (save() skips rewriting unchanged `context_json`);
   V011 adds real-target execution metadata to `eval_runs`; V012 adds
   `workspace_invitations`, `eval_cases.standard_version`, and
   `eval_runs.case_version_digest` / `target_deployment_version`; V013 adds the
   release-gate `service_tokens` and append-only `release_gate_checks` tables;
   V014 adds the `eval_experiments` claim columns (`claim_owner`,
   `claim_attempt`, `claim_request_key`, `claim_heartbeat_at`,
   `claim_lease_until`) used by shared claim/lease/heartbeat coordination.
   Runtime code validates these tables but does not create or upgrade them ad hoc.

### V014 deployment order (eval claim coordination)

1. Back up the database.
2. Drain every old worker and in-flight eval experiment. Old code does not
   understand the claim columns and can run concurrently with new code.
3. Inspect `eval_experiments` rows stuck in `running`; wait for them to finish
   or mark them `interrupted` manually before deploying.
4. Run `alembic upgrade head` (V013 → V014). SQLite upgrades in place via
   `initialize()`.
5. Deploy the new code. Never mix old and new workers on the same database.
6. To roll back: stop all eval jobs, verify no experiment is running, then
   `alembic downgrade V013`; the claim columns are dropped.

### Legacy databases created before Alembic

A database created by hand before this migration chain has no `alembic_version`
table and may lack columns that V001 assumes (for example `sessions.tenant_id`).
Running `alembic upgrade head` directly fails: `CREATE TABLE IF NOT EXISTS` keeps
the existing tables unchanged, but the tenant indexes created immediately after
them reference missing columns.

Upgrade such a database in four steps:

1. Back up with `pg_dump` and store the dump outside the repository tree
   (`.upgrade/backup/` is git-ignored).
2. Diff it against a database that has run V001 → V014, then
   `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` every missing non-generated column.
3. Insert the baseline row into `alembic_version` (or run `alembic stamp V001`)
   so the chain does not try to recreate existing tables.
4. Run `alembic upgrade head` and verify the V008–V014 columns, indexes and constraints.

Rows predating the multi-tenant model keep `tenant_id = NULL`; backfill them to a
real tenant before relying on tenant-scoped reads or governance aggregates:

```bash
# dry-run（缺省）：只统计匹配的孤儿会话
uv run python scripts/backfill_session_tenants.py --tenant-id <tenant-uuid>
# 实际写库：仅更新 tenant_id IS NULL 的行，可重复执行
uv run python scripts/backfill_session_tenants.py --tenant-id <tenant-uuid> --apply
```

### Historical plaintext `goal` backfill

The pre-1.7 encryption layer encrypted `research_goal` by typo while the actual
`ProjectContext` field is `goal`. Plaintext `goal` values written before the fix
are still readable, but are not encrypted at rest until backfilled:

```bash
# dry-run（缺省）：只统计会加密的行
uv run python scripts/encrypt_legacy_goal.py
# 实际写库：幂等；跳过 public_demo；必须配置 DATA_ENCRYPTION_KEY
uv run python scripts/encrypt_legacy_goal.py --apply
# 校验已有 enc:v1: goal 是否可用当前密钥解密
uv run python scripts/encrypt_legacy_goal.py --verify
```

Before rolling back to a pre-1.7 application (which does not decrypt `goal`),
either restore the pre-upgrade database dump or run
`uv run python scripts/encrypt_legacy_goal.py --decrypt --apply --allow-plaintext`
first.

### Historical audit/event redaction backfill (P0)

Pre-P0 audit snapshots and `session_events.payload` may contain evaluation free
text (`input_payload`, `expected_behavior`, `actual_output`, `human_comment`,
`judge_reason`, `pass_criteria`) or raw purge summaries. Back up the database
first, then drain all old workers before running the controlled backfill:

```bash
# dry-run（缺省）：只统计会修改的行
uv run python scripts/redact_legacy_audit_payloads.py
# 实际写库：按批事务化，可中断续跑、重复执行幂等
uv run python scripts/redact_legacy_audit_payloads.py --apply --batch-size 200
# 只处理归档并输出报告（报告不含原文）
uv run python scripts/redact_legacy_audit_payloads.py --apply \
  --tables audit_events_archive --report .upgrade/logs/audit-redaction.json
```

The script preserves `event_id`, `actor`, timestamps and existing
`before_hash`/`after_hash`; it records `_redaction_backfill` in metadata (or the
payload for `session_events`). Malformed JSON is reported and left untouched.
Restoring an old backup reintroduces the plaintext and requires re-running the
backfill.

### Context cache namespace migration (P0)

Context cache keys now use `session:ctx:v2:{tenant_id}:{session_id}`. Old
`session:ctx:{tenant_id}:{session_id}` keys are never read by the new code.
After draining old workers, remove only this application's legacy keys:

```bash
# dry-run（缺省）：只统计旧键
uv run python scripts/purge_legacy_context_cache.py
# 实际删除：只删除不以 session:ctx:v2: 开头的 session:ctx:* 键
uv run python scripts/purge_legacy_context_cache.py --apply
```

Restart every process afterwards to clear in-process `MemoryCache` entries.
Never use `FLUSHDB`; the script never touches other cache namespaces.


### SQLite (lite mode)

`storage/backends/sqlite_store.py::SQLiteSessionStore.initialize()` creates all tables inline
via DDL — no Alembic needed.

## Backends

| Module | Backend | Activation |
|--------|---------|------------|
| `storage/backends/postgres.py` | PostgreSQL | `STORAGE_BACKEND=postgres` (default) |
| `storage/backends/sqlite_store.py` | SQLite | `STORAGE_BACKEND=sqlite` |

## Cache

| Module | Backend | Activation |
|--------|---------|------------|
| `storage/cache.py` → `ContextCache` | Redis | Postgres mode |
| `storage/cache.py` → `MemoryCache` (from `storage/backends/memory_cache.py`) | In-process dict | SQLite / lite mode |
