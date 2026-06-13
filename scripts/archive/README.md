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
