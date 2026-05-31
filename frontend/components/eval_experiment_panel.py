# frontend/components/eval_experiment_panel.py
from __future__ import annotations

import streamlit as st


def render_eval_experiment_panel(
    *,
    datasets: list[dict],
    experiments: list[dict],
    eval_cases: list[dict],
    eval_runs: list[dict],
) -> None:
    """v0.8-alpha.2 dataset/experiment overview with Regression Gate status."""

    st.subheader("Eval Dataset / Experiment Regression Gate")
    st.caption(
        "v0.8-alpha.2: gate-relevant datasets and experiment comparisons now feed "
        "StageAdvancementDecision through the eval_regression rule."
    )

    col_cases, col_datasets, col_experiments, col_runs = st.columns(4)
    col_cases.metric("EvalCases", len(eval_cases))
    col_datasets.metric("Datasets", len(datasets))
    col_experiments.metric("Experiments", len(experiments))
    col_runs.metric("EvalRuns", len(eval_runs))

    with st.expander("Datasets", expanded=bool(datasets)):
        if not datasets:
            st.caption("No EvalDataset yet. Create one from Stage 3 EvalCases.")
        for dataset in datasets:
            st.markdown(
                f"**`{dataset.get('dataset_id')}`** · {dataset.get('name')} · "
                f"v{dataset.get('version')} · cases={len(dataset.get('case_ids') or [])}"
            )
            st.caption(
                f"source={dataset.get('source')} · scenario={dataset.get('scenario_type')} · "
                f"baseline={dataset.get('baseline_experiment_id') or '-'}"
            )

    with st.expander("Experiments", expanded=bool(experiments)):
        if not experiments:
            st.caption("No EvalExperiment yet.")
        for experiment in experiments:
            metrics = experiment.get("aggregate_metrics") or {}
            comparison = experiment.get("comparison_summary") or {}
            st.markdown(
                f"**`{experiment.get('experiment_id')}`** · {experiment.get('name')} · "
                f"{experiment.get('status')} · mode={experiment.get('run_mode')}"
            )
            st.caption(
                f"dataset={experiment.get('dataset_id')} · runs={len(experiment.get('run_ids') or [])} · "
                f"pass_rate={metrics.get('pass_rate', 0):.2f} · human_disagreement_rate={metrics.get('human_disagreement_rate', None)}"
            )
            if comparison:
                st.caption(
                    f"baseline={comparison.get('baseline_experiment_id') or experiment.get('baseline_experiment_id') or '-'} · "
                    f"gate_effect={comparison.get('gate_effect') or '-'}"
                )
                if comparison.get("regression_detected"):
                    st.error(
                        "Regression blocks Stage 3 advancement: "
                        + ", ".join(comparison.get("regression_reasons") or [])
                    )
                else:
                    st.success("No regression detected in comparison summary.")
