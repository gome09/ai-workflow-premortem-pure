# frontend/views/panels/eval_panels.py
from __future__ import annotations

import streamlit as st
from components.redteam_panel import render_redteam_panel
from controllers.eval_controller import (
    approve_redteam,
    create_dataset_from_stage3,
    create_experiment,
    create_redteam_dataset_and_refresh,
    generate_redteam,
    reject_redteam,
    run_all_cases,
    run_case,
    run_experiment,
    save_score,
    sync_redteam_case,
)
from labels import status_zh
from models.api_client import (
    get_redteam_coverage,
    list_eval_cases,
    list_eval_datasets,
    list_eval_experiments,
    list_eval_runs,
    list_redteam_cases,
)


def render_redteam_section() -> None:
    with st.expander("🛡️ 红队覆盖", expanded=False):
        redteam_cases = list_redteam_cases(st.session_state.session_id)
        redteam_coverage = get_redteam_coverage(st.session_state.session_id)
        render_redteam_panel(cases=redteam_cases, coverage=redteam_coverage)

        col_generate, col_dataset = st.columns(2)
        with col_generate:
            if st.button("🧪 生成红队用例草稿", use_container_width=True):
                generate_redteam()
        with col_dataset:
            if st.button("📦 创建红队数据集", use_container_width=True):
                create_redteam_dataset_and_refresh()

        for case in redteam_cases:
            case_id = case.get("redteam_case_id")
            if not case_id:
                continue
            cols = st.columns(3)
            with cols[0]:
                if case.get("status") == "draft" and st.button(
                    f"✅ 批准 {case_id}",
                    key=f"approve_redteam_{case_id}",
                    use_container_width=True,
                ):
                    approve_redteam(case_id)
            with cols[1]:
                if case.get("status") == "draft" and st.button(
                    f"📝 驳回 {case_id}",
                    key=f"reject_redteam_{case_id}",
                    use_container_width=True,
                ):
                    reject_redteam(case_id)
            with cols[2]:
                if case.get("status") == "approved" and st.button(
                    f"🔗 同步 {case_id}",
                    key=f"sync_redteam_{case_id}",
                    use_container_width=True,
                ):
                    sync_redteam_case(case_id)


def render_eval_panel() -> None:
    with st.expander("🧪 评测用例 / 数据集 / 实验", expanded=False):
        eval_cases = list_eval_cases(st.session_state.session_id)
        eval_runs = list_eval_runs(st.session_state.session_id)
        eval_datasets = list_eval_datasets(st.session_state.session_id)
        eval_experiments = list_eval_experiments(st.session_state.session_id)

        st.caption(
            "评测数据集 / 评测实验 / 回归门控 / 追踪回填门控均已在数据层面可用；"
            "运行时校验仍按指令延后执行。"
        )
        metric_cols = st.columns(4)
        metric_cols[0].metric("评测用例", len(eval_cases))
        metric_cols[1].metric("数据集", len(eval_datasets))
        metric_cols[2].metric("实验", len(eval_experiments))
        metric_cols[3].metric("评测运行", len(eval_runs))

        with st.expander("数据集 / 实验基础配置", expanded=bool(eval_datasets or eval_experiments)):
            dataset_name = st.text_input(
                "数据集名称",
                value="阶段三生成数据集",
                key="eval_dataset_name",
            )
            if st.button("📦 从阶段三创建数据集", use_container_width=True):
                create_dataset_from_stage3(dataset_name)

            if eval_datasets:
                dataset_options = {
                    f"{dataset.get('dataset_id')} · {dataset.get('name')}": dataset
                    for dataset in eval_datasets
                }
                selected_dataset_label = st.selectbox(
                    "选择数据集",
                    options=list(dataset_options.keys()),
                    key="selected_eval_dataset",
                )
                selected_dataset = dataset_options[selected_dataset_label]
                st.caption(
                    f"用例数={len(selected_dataset.get('case_ids') or [])} · "
                    f"来源={selected_dataset.get('source')} · "
                    f"基线={selected_dataset.get('baseline_experiment_id') or '-'}"
                )
                experiment_name = st.text_input(
                    "实验名称",
                    value=f"针对 {selected_dataset.get('name')} 的实验",
                    key="eval_experiment_name",
                )
                experiment_run_mode = st.selectbox(
                    "实验运行模式",
                    ["manual", "dry_run", "llm_node"],
                    index=1,
                    key="eval_experiment_run_mode",
                )
                baseline_options = {"[无]": None}
                baseline_options.update(
                    {
                        f"{exp.get('experiment_id')} · {exp.get('name')}": exp.get("experiment_id")
                        for exp in eval_experiments
                        if exp.get("dataset_id") == selected_dataset.get("dataset_id")
                    }
                )
                selected_baseline_label = st.selectbox(
                    "基线实验",
                    options=list(baseline_options.keys()),
                    key="selected_eval_baseline",
                )
                if st.button("🧪 创建实验", use_container_width=True):
                    create_experiment(
                        selected_dataset.get("dataset_id"),
                        experiment_name,
                        experiment_run_mode,
                        baseline_options[selected_baseline_label],
                    )

            if eval_experiments:
                st.markdown("**实验列表**")
                for experiment in eval_experiments:
                    metrics = experiment.get("aggregate_metrics") or {}
                    comparison = experiment.get("comparison_summary") or {}
                    st.markdown(
                        f"- `{experiment.get('experiment_id')}` · {experiment.get('name')} · "
                        f"{status_zh(experiment.get('status'))} · 模式={experiment.get('run_mode')} · "
                        f"通过率={metrics.get('pass_rate', 0):.2f}"
                    )
                    disagreement_rate = metrics.get("human_disagreement_rate")
                    if disagreement_rate is not None:
                        st.caption(
                            f"人工校准 {metrics.get('human_calibration_count', 0)} 次 · "
                            f"与自动评审分歧率={disagreement_rate:.2f}"
                        )
                    if experiment.get("status") in {"created", "failed"}:
                        if st.button(
                            f"▶️ 运行 {experiment.get('experiment_id')}",
                            key=f"run_experiment_{experiment.get('experiment_id')}",
                            use_container_width=True,
                        ):
                            run_experiment(experiment.get("experiment_id"))
                    if comparison:
                        if comparison.get("regression_detected"):
                            st.warning(f"对比检测到回归：{comparison.get('regression_reasons')}")
                        else:
                            st.success("对比结果：未检测到回归。")

        run_mode = st.selectbox(
            "评测用例运行模式", ["manual", "dry_run", "llm_node"], key="eval_run_mode"
        )
        if eval_cases:
            col_run_all, col_refresh_runs = st.columns(2)
            with col_run_all:
                if st.button("▶️ 运行全部评测用例", use_container_width=True):
                    run_all_cases(run_mode)
            with col_refresh_runs:
                st.caption(f"评测运行数：{len(eval_runs)}")

            for case in eval_cases:
                st.markdown(
                    f"**`{case.get('eval_id')}`** · 节点={case.get('target_node_id')} · "
                    f"{case.get('scenario_type')} · 通过={case.get('passed')}"
                )
                st.caption("测试输入：" + (case.get("input_payload") or "")[:300])
                st.caption("预期行为：" + (case.get("expected_behavior") or "")[:300])
                pass_criteria = case.get("pass_criteria") or []
                if pass_criteria:
                    st.caption("通过标准：" + "；".join(pass_criteria)[:300])
                if st.button(
                    "▶️ 运行该用例",
                    key=f"run_eval_{case.get('eval_id')}",
                    use_container_width=True,
                ):
                    run_case(case.get("eval_id"), run_mode)
                case_runs = [run for run in eval_runs if run.get("eval_id") == case.get("eval_id")]
                if case_runs:
                    latest_run = case_runs[-1]
                    st.caption(
                        "最近一次运行："
                        f"{latest_run.get('run_id')} · 状态={status_zh(latest_run.get('status'))} · "
                        f"评审结果={latest_run.get('judge_result')}"
                    )
                    judge_reason = latest_run.get("judge_reason") or ""
                    violated = latest_run.get("violated_criteria") or []
                    if judge_reason:
                        st.caption(f"评审理由：{judge_reason[:300]}")
                    if violated:
                        st.caption("未满足标准：" + "；".join(violated)[:300])
                score_key = f"eval_score_{case.get('eval_id')}"
                comment_key = f"eval_comment_{case.get('eval_id')}"
                pass_key = f"eval_passed_{case.get('eval_id')}"
                actual_key = f"eval_actual_{case.get('eval_id')}"
                actual_value = st.text_area(
                    "实际输出",
                    value=case.get("actual_output") or "",
                    key=actual_key,
                    height=90,
                )
                score_value = st.slider(
                    "人工评分（1-5）",
                    1,
                    5,
                    int(case.get("human_score") or 3),
                    key=score_key,
                )
                passed_value = st.selectbox("人工结论", ["未定", "通过", "不通过"], key=pass_key)
                comment_value = st.text_input(
                    "评分备注", value=case.get("human_comment") or "", key=comment_key
                )
                passed_bool = None if passed_value == "未定" else passed_value == "通过"
                if st.button(
                    "💾 保存评分",
                    key=f"score_eval_{case.get('eval_id')}",
                    use_container_width=True,
                ):
                    save_score(
                        case.get("eval_id"),
                        score_value,
                        comment_value,
                        passed_bool,
                        actual_value,
                    )
                st.divider()
        else:
            st.caption("暂无 EvalCase。阶段三压测完成后会自动生成。")
