# Archived Acceptance Scripts

> **Historical reference only.** These scripts are NOT part of the current acceptance entry point.

This directory contains acceptance probe scripts from earlier development phases (AC-05 through AC-08). They are retained for historical traceability only.

## Current Acceptance Entry Point

The current acceptance entry point is the 13 scripts in `scripts/acceptance/` (parent directory, non-archived):

- `ac09a_report_artifact_export.py`
- `ac09b_fix_reports_router_testclient.py`
- `ac09b_report_api_persistence.py`
- `ac09c_pg_report_artifacts_persistence.py`
- `ac10a_streamlit_report_panel_minimum.py`
- `ac10b_streamlit_stage_gate_actions_minimum.py`
- `ac10c_streamlit_evidence_panel_minimum.py`
- `ac10d_streamlit_safety_eval_panels_minimum.py`
- `ac10e_streamlit_audit_workbench_closure.py`
- `ac10f_workbench_runtime_smoke.py`
- `ac11a_interrupt_adapter_boundary.py`
- `ac11b_interrupt_api_default_mode_smoke.py`
- `ac11c_interrupt_explicit_mode_runtime_smoke.py`

**Current acceptance baseline:** 13/13 scripts, 707/707 checks, 148/148 pytest, 61 OpenAPI paths.
