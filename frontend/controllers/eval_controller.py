# frontend/controllers/eval_controller.py
from __future__ import annotations

import streamlit as st
from models.api_client import (
    approve_redteam_case,
    create_eval_dataset_from_stage3,
    create_eval_experiment,
    create_redteam_dataset,
    generate_redteam_cases,
    invalidate_session_cache,
    reject_redteam_case,
    run_eval_cases,
    run_eval_experiment,
    run_single_eval_case,
    score_eval_case,
    sync_redteam_case_to_eval,
)
from models.session_state import refresh_actions


def run_all_cases(run_mode: str, target_config: dict | None = None) -> None:
    result = run_eval_cases(
        st.session_state.session_id, None, run_mode, target_config=target_config
    )
    if result:
        refresh_actions()
        st.success(f"已创建 {len(result.get('created_runs', []))} 次评测运行。")
        st.rerun()


def run_case(eval_id: str, run_mode: str, target_config: dict | None = None) -> None:
    result = run_single_eval_case(
        st.session_state.session_id, eval_id, run_mode, target_config=target_config
    )
    if result:
        refresh_actions()
        st.rerun()


def save_score(
    eval_id: str,
    human_score: int,
    human_comment: str,
    passed: bool | None,
    actual_output: str,
) -> None:
    if score_eval_case(
        st.session_state.session_id,
        eval_id,
        human_score,
        human_comment,
        passed,
        actual_output,
    ):
        refresh_actions()
        st.rerun()


def create_dataset_from_stage3(dataset_name: str) -> None:
    dataset = create_eval_dataset_from_stage3(
        st.session_state.session_id,
        dataset_name,
        "由当前阶段三评测用例创建。",
    )
    if dataset:
        invalidate_session_cache(st.session_state.session_id)
        st.success(f"数据集已创建：{dataset.get('dataset_id')}")
        st.rerun()


def create_experiment(
    dataset_id: str,
    experiment_name: str,
    run_mode: str,
    baseline_experiment_id: str | None,
    target_config: dict | None = None,
) -> None:
    experiment = create_eval_experiment(
        st.session_state.session_id,
        dataset_id,
        experiment_name,
        run_mode,
        baseline_experiment_id,
        target_config=target_config,
    )
    if experiment:
        invalidate_session_cache(st.session_state.session_id)
        st.success(f"实验已创建：{experiment.get('experiment_id')}")
        st.rerun()


def run_experiment(experiment_id: str) -> None:
    result = run_eval_experiment(
        st.session_state.session_id,
        experiment_id,
        dry_run_only=True,
    )
    if result:
        refresh_actions()
        st.success("实验已运行或已记录。")
        st.rerun()


def generate_redteam() -> None:
    created = generate_redteam_cases(st.session_state.session_id)
    st.success(f"已生成 {len(created)} 条红队用例草稿。")
    refresh_actions()
    st.rerun()


def create_redteam_dataset_and_refresh() -> None:
    dataset = create_redteam_dataset(st.session_state.session_id)
    if dataset:
        st.success(f"数据集已创建：{dataset.get('dataset_id')}")
        refresh_actions()
        st.rerun()


def approve_redteam(case_id: str) -> None:
    approve_redteam_case(st.session_state.session_id, case_id, "已在复核工作台批准")
    refresh_actions()
    st.rerun()


def reject_redteam(case_id: str) -> None:
    reject_redteam_case(st.session_state.session_id, case_id, "已在复核工作台驳回")
    refresh_actions()
    st.rerun()


def sync_redteam_case(case_id: str) -> None:
    eval_case = sync_redteam_case_to_eval(st.session_state.session_id, case_id)
    if eval_case:
        st.success(f"已同步为评测用例：{eval_case.get('eval_id')}")
    refresh_actions()
    st.rerun()
