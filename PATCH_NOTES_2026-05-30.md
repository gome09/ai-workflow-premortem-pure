# Patch Notes — Acceptance Package Repair

Date: 2026-05-30

This package repairs the acceptance reproducibility issues found in the clean local-preview archive.

## Changes

1. Restored `.env.acceptance` as a deterministic dummy-key acceptance template.
2. Added explicit `Version: 0.8.0-alpha.11` and `Source version` metadata to `PACKAGE_MANIFEST.txt`.
3. Updated `scripts/version_check.py` so it accepts either `Version:` or `Source version:` markers in the manifest.
4. Updated `PACKAGE_MANIFEST.txt` cleanup notes and included-file list so they match the packaged contents.

## Validation Performed

- `python -S scripts/version_check.py`
- `python -S -m compileall -q api core frontend graph stages storage tools tests scripts`

This repair preserves the original project boundary: ready for personal / trusted small-team local preview, not production SaaS or public internet deployment.
