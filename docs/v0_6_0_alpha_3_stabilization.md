# v0.6.0-alpha.3 Stabilization Notes

This patch applies the previously planned stage-control stabilization work to the real `v0.6.0-alpha.2` source package.

## Scope

The patch does not redesign the product. It preserves:

- four deterministic product stages;
- `single_step` as the default stable path;
- `PendingHumanAction` as the authoritative business review object;
- `langgraph_interrupt` as an experimental adapter;
- existing Evidence, Safety, Eval, Report, and Streamlit Review Workbench modules.

## What changed

### 1. Version and package metadata

Updated:

```text
core/version.py
pyproject.toml
PACKAGE_MANIFEST.txt
README.md
ROADMAP.md
CHANGELOG.md
```

The project now identifies as `0.6.0-alpha.3`.

### 2. Stage transition policy

`graph/transition_policy.py` now blocks advancement on:

- unresolved blocking actions;
- rejected critical review actions;
- unresolved escalations;
- parser errors;
- open high/critical safety findings;
- Stage 1 high-risk evidence readiness gaps;
- Stage 2 high-risk failure-mode coverage or policy gaps;
- Stage 3 failed high-risk eval cases/runs;
- Stage 4 final critical safety or parser blockers.

### 3. Action/interrupt boundary

`core/oversight_service.py` no longer calls `graph.interrupts` directly.

Action resolution remains a business operation. Execution-mode-specific synchronization is coordinated by:

```text
core/execution_service.py
core/session_service.py
```

### 4. Reports

`core/report_service.py` now exposes:

```text
stage_readiness
unresolved_governance_items
```

These sections help reviewers understand why a stage is blocked and what must be handled before completion.

### 5. Safety policy coverage

`tools/safety_classifier.py` now also detects high-risk Stage 1 failure modes not covered by Stage 2 workflow nodes.

## Deferred validation

Per instruction, this patch does not run pytest or runtime validation. A narrow static syntax check was performed only on modified Python files before packaging. After all function boundaries are frozen, run one unified validation pass covering:

```text
python scripts/version_check.py
python -m compileall -q .
pytest
single_step end-to-end smoke flow
langgraph_interrupt resume-once flow
report export JSON/Markdown flow
```
