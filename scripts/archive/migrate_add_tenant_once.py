#!/usr/bin/env python3
"""
One-time migration: create legacy tenant and backfill tenant_id for existing data.
Run once after Phase A deployment on instances with existing data:
    docker compose exec api python scripts/migrate_add_tenant.py
"""

import os

import psycopg

LEGACY_TENANT_ID = "00000000-0000-0000-0000-000000000001"
LEGACY_TENANT_NAME = "legacy"

DSN = (
    f"postgresql://{os.environ.get('POSTGRES_USER', 'postgres')}:"
    f"{os.environ.get('POSTGRES_PASSWORD', 'localpass')}@"
    f"{os.environ.get('POSTGRES_HOST', 'localhost')}:"
    f"{os.environ.get('POSTGRES_PORT', '5432')}/"
    f"{os.environ.get('POSTGRES_DB', 'ai_workflow')}"
)


def main():
    with psycopg.connect(DSN) as conn:
        conn.execute(
            "INSERT INTO tenants (tenant_id, name) VALUES (%s, %s) ON CONFLICT (tenant_id) DO NOTHING",
            (LEGACY_TENANT_ID, LEGACY_TENANT_NAME),
        )
        r1 = conn.execute(
            "UPDATE sessions SET tenant_id = %s WHERE tenant_id IS NULL", (LEGACY_TENANT_ID,)
        )
        print(f"sessions updated: {r1.rowcount}")
        r2 = conn.execute(
            "UPDATE session_events SET tenant_id = %s WHERE tenant_id IS NULL", (LEGACY_TENANT_ID,)
        )
        print(f"session_events updated: {r2.rowcount}")
        r3 = conn.execute(
            "UPDATE human_actions SET tenant_id = %s WHERE tenant_id IS NULL", (LEGACY_TENANT_ID,)
        )
        print(f"human_actions updated: {r3.rowcount}")
        conn.commit()
    print("Migration complete.")


if __name__ == "__main__":
    main()
