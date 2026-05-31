# Clean Package Report

This package was cleaned from `ai-workflow-premortem-e2e-validated.zip`.

## Result

- Source/tests/docs retained.
- Runtime logs, raw live API payloads, bulky archived exports, debug JSON, and stale handoff/link-recovery artifacts removed.
- No `.env` file is included. `.env.example` is retained.
- `.env.acceptance` is retained intentionally as a dummy acceptance environment template. It contains no real secrets and is safe for local-preview acceptance use.

## Removed Items

| Path | Files | Bytes |
|------|------:|------:|
| `logs` | 40 | 6532821 |
| `docs/archive` | 4 | 222775879 |
| `debug_eval_cases.json` | 1 | 14946 |
| `debug_stage3_resolution.json` | 1 | 20536 |
| `stage1_response.json` | 1 | 9247 |
| `stage1_start_response.json` | 1 | 9247 |
| `stage1_resolution.json` | 1 | 1093 |
| `scripts/continue_e2e_s2_s4.py` | 1 | 7043 |
| `scripts/live_e2e_medication_monitor.py` | 1 | 5919 |
| `scripts/run_e2e_medication.py` | 1 | 14685 |
| `scripts/smoke_final_validation.py` | 1 | 10950 |
| `ALPHA10_SOURCE_FREEZE_CHECK.md` | 1 | 2765 |
| `ALPHA10_STAGE_ADVANCEMENT_CLOSURE_SUMMARY.md` | 1 | 2021 |
| `ALPHA11_FREEZE_FIX.md` | 1 | 2193 |
| `DOWNLOAD_LINK_RECOVERY.md` | 1 | 1455 |
| `FILE_LINK_RECOVERY.md` | 1 | 1455 |
| `FILE_LINK_RECOVERY_ALPHA10.md` | 1 | 941 |
| `FILE_LINK_RECOVERY_ALPHA10_SOURCE_FREEZE_CHECK.md` | 1 | 1226 |
| `FILE_LINK_RECOVERY_ALPHA11_FREEZE_FIX.md` | 1 | 1031 |
| `IMPLEMENTATION_PATCH_SUMMARY.md` | 1 | 2055 |
| `OPEN_SOURCE_REPAIR_NOTES.md` | 1 | 1541 |
| `PACKAGE_HANDOFF_ALPHA11.md` | 1 | 754 |
| `PATCH_MANIFEST_ALPHA10_SOURCE_FREEZE_CHECK.md` | 1 | 1380 |
| `PATCH_MANIFEST_ALPHA10_V080.md` | 1 | 1718 |
| `PATCH_MANIFEST_ALPHA11_FREEZE_FIX.md` | 1 | 1078 |
| `PATCH_MANIFEST_ALPHA1_V080.md` | 1 | 1164 |
| `PATCH_MANIFEST_ALPHA2_V080.md` | 1 | 1213 |
| `PATCH_MANIFEST_ALPHA3_V080.md` | 1 | 1104 |
| `PATCH_MANIFEST_ALPHA4.md` | 1 | 1200 |
| `PATCH_MANIFEST_ALPHA4_V080.md` | 1 | 661 |
| `PATCH_MANIFEST_ALPHA5_V080.md` | 1 | 703 |
| `PATCH_MANIFEST_ALPHA6_V080.md` | 1 | 752 |
| `PATCH_MANIFEST_ALPHA8_V080.md` | 1 | 933 |
| `PATCH_MANIFEST_ALPHA9_V080.md` | 1 | 1956 |
| `SOURCE_PATCH_NOTES_ALPHA2.md` | 1 | 383 |
| `DOCS_STATUS_CLEANUP_REPORT.md` | 1 | 7167 |

## Notes

- The active validation state remains documented in `docs/validation-status.md`, `docs/e2e-results-summary.md`, `docs/stage3-risk-adaptive-gate.md`, and the two `LIVE_E2E_*_REPORT.md` files.
- Raw E2E payloads were intentionally excluded from the clean distribution.
