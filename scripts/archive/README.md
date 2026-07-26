# Archived Scripts

This directory contains scripts that are no longer part of the current production workflow.

## migrate_add_tenant_once.py

Archived from `scripts/migrate_add_tenant.py` during v1.0 cleanup.

One-time database migration: creates the legacy tenant record and backfills `tenant_id`
for pre-tenant sessions, session_events, and human_actions rows.

This script was intended to run once after the Phase A (tenant support) deployment on
instances with existing data. It is not part of any repeatable migration chain and is
not invoked by Alembic. Retained for reference only.

**Do not run again** — re-running is idempotent for the INSERT but could mask issues
in a multi-tenant deployment.

## 2026-07-27 cleanup

Removed three tracked but unusable scripts after reference and behavior review:

- `stage_advancement_source_freeze_audit_alpha11.py` hard-coded obsolete alpha-version assumptions and paths that no longer exist.
- `live_e2e_low_risk_room_booking.py` and `live_e2e_student_management_v2.py` called protected session/stage endpoints without registering, logging in, or sending an Authorization header, so they return 401 against the current API.

None was called by Makefile, CI, production code, or the current test suite. Their history remains recoverable from Git; current authenticated acceptance coverage lives in `scripts/live_e2e_four_stage.py` and `tests/`.
