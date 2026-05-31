# frontend/components/gate_panel.py
from __future__ import annotations

import streamlit as st


def render_gate_panel(
    stage_readiness: dict,
    stage_resolution: dict | None = None,
    stage_advancement_decisions: dict | None = None,
) -> None:
    """Stage-gate panel aligned with the current decision/envelope contract."""

    st.subheader("Stage Gate Panel")
    if not stage_readiness:
        st.caption("No stage readiness data available.")
        return

    stage_resolution = stage_resolution or {}
    decisions = stage_advancement_decisions or {}
    by_stage = stage_resolution.get("by_stage") or {}

    for key in sorted(stage_readiness.keys()):
        item = stage_readiness.get(key) or {}
        stage_id = item.get("stage_id", key.replace("stage_", ""))
        decision = decisions.get(str(stage_id)) or decisions.get(key) or {}
        blockers = item.get("blockers") or []
        can_continue = item.get("can_continue", False)
        version = item.get("stage_output_version", 1)
        lifecycle = decision.get("stage_lifecycle") or item.get("stage_lifecycle", "")

        label = (
            f"✅ Stage {stage_id} v{version} · can advance"
            if can_continue
            else f"🧭 Stage {stage_id} v{version} · {len(blockers)} blocker(s)"
        )
        with st.expander(label, expanded=bool(blockers)):
            st.caption(
                f"lifecycle: `{lifecycle}` · decision_source: "
                f"`{decision.get('decision_source', 'stage_readiness')}`"
            )
            if decision:
                st.caption(
                    f"reason: `{decision.get('decision_reason')}` · "
                    f"hard={decision.get('hard_blockers_count', 0)} · "
                    f"executable={decision.get('executable_operations_count', 0)}"
                )
                if decision.get("trace_id"):
                    st.caption(f"trace_id: `{decision.get('trace_id')}`")
            if item.get("block_reason"):
                st.warning(item["block_reason"])

            for blocker in blockers:
                is_regression = blocker.get("blocker_type") == "eval_regression"
                is_trace_backfill = blocker.get("blocker_type") == "trace_backfill_gap"
                if is_regression or is_trace_backfill:
                    st.error(
                        f"`{blocker.get('blocker_id')}` "
                        f"[{blocker.get('severity')}/{blocker.get('rule_id') or blocker.get('blocker_type')}] "
                        f"{blocker.get('message')}"
                    )
                else:
                    st.markdown(
                        f"- `{blocker.get('blocker_id')}` "
                        f"[{blocker.get('severity')}/{blocker.get('rule_id') or blocker.get('blocker_type')}] "
                        f"{blocker.get('message')}"
                    )
                metadata = blocker.get("metadata") or {}
                st.caption(
                    f"required_resolution={blocker.get('required_resolution')} · "
                    f"action_id={blocker.get('action_id') or '-'} · "
                    f"source={blocker.get('source_type') or '-'}:{blocker.get('source_id') or '-'}"
                )
                if is_regression and metadata:
                    st.caption(
                        f"dataset={metadata.get('dataset_id') or '-'} · "
                        f"experiment={metadata.get('experiment_id') or '-'} · "
                        f"baseline={metadata.get('baseline_experiment_id') or '-'} · "
                        f"status={metadata.get('decision_status') or metadata.get('blocking_reason') or '-'}"
                    )
                if is_trace_backfill and metadata:
                    st.caption(
                        f"gap={metadata.get('gap_type') or '-'} · "
                        f"eligible_traces={metadata.get('eligible_trace_count', 0)} · "
                        f"datasets={len(metadata.get('trace_backfill_dataset_ids') or [])}"
                    )

            operations = decision.get("required_operations") or by_stage.get(key) or []
            if operations:
                st.markdown("**Resolution operations**")
                for op in operations:
                    with st.expander(
                        f"{op.get('required_resolution')} · {op.get('blocker_type')}",
                        expanded=False,
                    ):
                        if op.get("frontend_hint"):
                            st.markdown(op["frontend_hint"])
                        if op.get("api_path"):
                            st.caption(f"API: {op.get('api_method')} {op.get('api_path')}")
                        if op.get("payload_hint"):
                            st.json(op["payload_hint"])
                        st.caption(
                            "current operation executor contract: execute this via the dedicated "
                            "domain panel/API, then refresh StageAdvancementDecision. Runtime "
                            "validation remains deferred until the unified validation pass."
                        )
                        if op.get("can_execute_via_api") and op.get("api_path"):
                            st.info(
                                "Executable operation binding is available; use the matching Eval, Red Team, Trace, Evidence, Safety, or Stage panel action."
                            )
                        elif op.get("metadata", {}).get("contract_api_capable"):
                            st.warning(
                                "Operation is API-capable in the contract, but this blocker is missing the required source id binding."
                            )
