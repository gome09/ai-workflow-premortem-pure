# frontend/components/eval_panel.py
from __future__ import annotations

import streamlit as st


def render_eval_panel(eval_cases: list[dict], eval_runs: list[dict] | None = None) -> None:
    """Display EvalCase list with linked EvalRuns, showing status, output,
    and human scoring fields. Does NOT include API action buttons (handled
    inline in app.py via official eval API)."""
    st.subheader("Eval Cases")
    if not eval_cases:
        st.caption("No eval cases recorded.")
        return

    runs = eval_runs or []
    failed_count = sum(
        1 for r in runs if r.get("judge_result") == "failed" or r.get("status") == "failed"
    )
    passed_count = sum(1 for r in runs if r.get("judge_result") == "passed")
    st.caption(
        f"{len(eval_cases)} cases · "
        f"{len(runs)} runs · "
        f"{passed_count} passed · "
        f"{failed_count} failed"
    )

    for case in eval_cases:
        eval_id = case.get("eval_id", "")
        scenario = case.get("scenario_type", "")
        node = case.get("target_node_id", "")
        passed = case.get("passed")
        human_score = case.get("human_score")

        passed_label = (
            "✅ passed" if passed is True else "❌ failed" if passed is False else "⏳ unscored"
        )
        score_label = f"score={human_score}" if human_score is not None else "unscored"

        with st.expander(
            f"`{eval_id}` · {scenario} · node={node} · {passed_label} · {score_label}",
            expanded=(passed is False),
        ):
            st.code(eval_id, language="text")
            st.caption(
                f"Scenario: {scenario}  ·  Target node: {node}  ·  {passed_label}  ·  {score_label}"
            )

            input_payload = case.get("input_payload") or ""
            if input_payload:
                st.caption(f"Input: {input_payload[:300]}")
            expected = case.get("expected_behavior") or ""
            if expected:
                st.caption(f"Expected: {expected[:300]}")
            pass_criteria = case.get("pass_criteria") or []
            if pass_criteria:
                with st.expander(f"Pass criteria ({len(pass_criteria)})", expanded=False):
                    for criterion in pass_criteria:
                        st.markdown(f"- {criterion}")
            actual = case.get("actual_output") or ""
            if actual:
                st.caption(f"Actual output: {actual[:300]}")
            if case.get("human_comment"):
                st.caption(f"Review note: {case['human_comment']}")

            # Linked runs
            case_runs = [r for r in runs if r.get("eval_id") == eval_id]
            if case_runs:
                with st.expander(f"EvalRuns ({len(case_runs)})", expanded=False):
                    for run in case_runs:
                        run_id = run.get("run_id", "")
                        run_status = run.get("status", "?")
                        judge = run.get("judge_result", "?")
                        judge_reason = run.get("judge_reason", "")
                        run_icon = (
                            "❌"
                            if judge == "failed" or run_status == "failed"
                            else "✅"
                            if judge == "passed"
                            else "⏳"
                        )
                        st.markdown(f"{run_icon} `{run_id}` · status={run_status} · judge={judge}")
                        if judge_reason:
                            st.caption(f"Reason: {judge_reason}")
                        if run.get("violated_criteria"):
                            st.caption("Violated: " + ", ".join(run.get("violated_criteria", [])))
            else:
                st.caption("No EvalRuns for this case yet.")

            if passed is False:
                st.warning("This eval case has not passed — may indicate unresolved coverage gaps.")
