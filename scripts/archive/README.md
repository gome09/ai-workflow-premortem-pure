# Archived Scripts

This directory contains scripts that are no longer part of the current v1.0 production workflow.

## stage_advancement_source_freeze_audit_alpha11.py

Archived from `scripts/static/stage_advancement_source_freeze_audit.py` during v1.0 cleanup.

This script validates v0.8.0-alpha.11 release assumptions that no longer match the current v1.0 codebase.

Known stale assumptions:
- Expected `APP_VERSION = "0.8.0-alpha.11"` — current is `"1.0.0"`
- Expected `PACKAGE_STAGE = "v0.8.0-alpha.11-freeze-fix"` — current is `"v1.0.0"`
- Expected `ROADMAP.md` to exist at the project root — file does not exist
- Expected `docs/stage_advancement_api_return_audit_alpha11.md` to exist — file does not exist
- Checked for `"policy_version": "v0.8.0-alpha.9"` in `eval_regression_policy.py` — that file now uses `APP_VERSION` dynamically

Do not use this script for current release validation. For v1.0 gate contract consistency
checks, add equivalent assertions to the pytest suite under `tests/`.

## migrate_add_tenant_once.py

Archived from `scripts/migrate_add_tenant.py` during v1.0 cleanup.

One-time database migration: creates the legacy tenant record and backfills `tenant_id`
for pre-tenant sessions, session_events, and human_actions rows.

This script was intended to run once after the Phase A (tenant support) deployment on
instances with existing data. It is not part of any repeatable migration chain and is
not invoked by Alembic. Retained for reference only.

**Do not run again** — re-running is idempotent for the INSERT but could mask issues
in a multi-tenant deployment.

## live_e2e_low_risk_room_booking.py

Archived from `scripts/live_e2e_low_risk_room_booking.py` during v1.0 cleanup.

Manual live E2E script that drives a full Stage 0–4 workflow through the real API for
the enterprise meeting-room booking scenario. Requires a running local API on port 8000.

Not part of CI. Retained for manual acceptance testing reference.

## live_e2e_student_management_v2.py

Archived from `scripts/live_e2e_student_management_v2.py` during v1.0 cleanup.

Manual live E2E script that drives a full Stage 0–4 workflow through the real API for
the university student management scenario. Requires a running local API on port 8000.

Not part of CI. Retained for manual acceptance testing reference.
