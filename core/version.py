"""Single source of truth for application and report versions.

v0.8.0-alpha.11 keeps the alpha.10 stage-advancement contract intact while:
- aligning ROADMAP/package metadata with the actual package stage;
- sourcing Eval Regression policy metadata from this version module;
- correcting the static API return audit for EvalDataset gate-affecting flows;
- adding a non-runtime source-freeze audit script for later manual checks;
- improving frontend StageOperationEnvelope consumption coordination.

Docker Final Local-Preview Acceptance (2026-05-30): PASS.
Runtime smoke (health, OpenAPI, container logs) validated under Docker Compose.
"""

APP_VERSION = "0.8.0-alpha.11"
REPORT_SCHEMA_VERSION = "0.8.0-alpha.11"
APP_STATUS = "source-level-v080-alpha11-freeze-fix"
PACKAGE_STAGE = "v0.8.0-alpha.11-freeze-fix"
RUNTIME_VALIDATION = "docker_final_local_preview_pass"
