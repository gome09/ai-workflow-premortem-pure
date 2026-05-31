# v0.6.0-alpha.8 Stage Advancement Closure & Coordination

This patch is based on the real uploaded `v0.6.0-alpha.7` project source. It does not redesign the project and does not run pytest, API startup, Streamlit startup, Docker validation, or runtime workflow validation.

## Scope

The alpha.8 patch closes the stage-advancement loop around the existing design:

```text
StageBlocker
→ StageResolutionOperation
→ executable operation or explicit sync action
→ state mutation / action queue repair
→ audit event
→ refreshed stage gate / report explanation
```

The stable workflow execution mode remains `single_step`. `langgraph_interrupt` remains experimental.

## Added

- `core/stage_operation_service.py`
- executable stage operation APIs:
  - `POST /sessions/{session_id}/stages/{stage_id}/rerun`
  - `POST /sessions/{session_id}/stages/{stage_id}/revise`
  - `POST /sessions/{session_id}/stages/{stage_id}/rollback`
  - `POST /sessions/{session_id}/stages/{stage_id}/sync-review-actions`

## Changed

- Version metadata is aligned to `0.6.0-alpha.8`.
- Stage resolution contracts now expose executable stage mutation endpoints for rerun/revise/back.
- `StageResolutionOperation.api_path` supports `{stage_id}`.
- Parser, policy-gap, evidence-gap, and eval-coverage edits require complete `structured_output`.
- Stage 3 high-risk EvalCase coverage gaps are blockers instead of warnings.
- High-risk EvalRun `needs_review` results now create/reuse blocking review actions.
- Stage 3 structured edits resync EvalCase records before regenerating review actions.
- Review Workbench shows alpha.8 operation cards and can call stage mutation/sync endpoints.

## Deferred by instruction

- pytest
- API startup
- Streamlit startup
- Docker validation
- real LLM calls
- Tavily calls
- runtime workflow validation


## Doc/test/core alignment follow-up

This package now includes a dependency-light alignment contract that checks Markdown and test acceptance notes against the real alpha.8 source-of-truth files:

```text
docs/v0_6_0_alpha_8_core_code_alignment_contract.md
tests/ACCEPTANCE_TEST_ALIGNMENT_ALPHA8.md
tests/test_alpha8_doc_core_alignment_contract.py
```

The alignment test parses `core/stage_advancement_contract.py` and `api/routers/stage.py` directly. It is intended to prevent stale Markdown or hand-written acceptance notes from drifting away from the actual blocker/resolution and stage-router contracts.

This follow-up modifies documentation and tests only. It does not modify core workflow logic, graph behavior, API behavior, storage behavior, frontend behavior, or external-service behavior.
