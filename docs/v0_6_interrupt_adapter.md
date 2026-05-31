# v0.6.0-alpha.2 Checkpoint-backed Interrupt Adapter Source Patch

> Historical note: this document describes the alpha.2 interrupt adapter patch. It is superseded operationally by `docs/v0_6_0_alpha_3_stabilization.md`, which keeps the adapter experimental and centralizes action/interrupt synchronization in the execution/session coordination layer.

Status: experimental source patch, not yet beta-verified.

This patch follows the agreed phase plan and does not redesign the project. It keeps the deterministic `single_step` runner as the default path and adds the next v0.6 adapter layer behind `WORKFLOW_EXECUTION_MODE=langgraph_interrupt`.

## Implemented

1. Added `graph/interrupt_gate.py`.
   - Calls LangGraph `interrupt(payload)` only at a review gate.
   - Performs no LLM calls, no search calls, and no stage parsing.
   - Avoids repeated expensive stage execution when LangGraph resumes a node from the top.

2. Reworked `graph/langgraph_interrupt_runner.py`.
   - Builds a one-turn graph, not a full auto-running workflow.
   - Runs at most one deterministic `run_one_step(ctx)` call per user turn.
   - Routes to the review interrupt gate only when a blocking `PendingHumanAction` exists.
   - Uses PostgreSQL checkpointer when available and falls back to memory in local/dev mode.

3. Wired action resolution to resume consumption.
   - `resolve_action()` still updates the business action first.
   - If the configured mode is `langgraph_interrupt`, a resumable interrupt is consumed with `Command(resume=...)`.
   - Rejected, cancelled, superseded, or still-pending actions are never resumed.

4. Added execution metadata.
   - `/health` returns `workflow_execution_mode` and `interrupt_adapter_status`.
   - Reports include `adapter_level`, `resume_consumed_count`, `pending_resume_count`, and `resume_error_count`.
   - Streamlit shows resumed-but-unconsumed and cancelled records in the interrupt debug panel.

## Preserved constraints

- `PendingHumanAction` remains the product/business source of truth.
- `InterruptRecord` remains an execution mapping layer.
- `single_step` remains the stable default.
- The app is not converted into a general workflow builder.
- Streamlit remains the front-end.
- PDF export and multi-user permission work remain out of scope.
- pytest/runtime verification is deferred until the v0.6 implementation is frozen.

## Validation to run before beta tagging

1. `single_step` default path still behaves exactly as before.
2. `langgraph_interrupt` creates a checkpoint-backed interrupt for blocking actions.
3. `approve`, `verified`, and valid `edit` consume `Command(resume=...)` exactly once.
4. `reject`, unresolved `escalate`, cancelled, and superseded actions do not resume.
5. Resume does not re-run the stage LLM/search/parser node.
6. Reports and Streamlit reflect the real execution mode and resume consumption state.
