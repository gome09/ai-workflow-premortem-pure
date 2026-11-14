# frontend/controllers/eval_controller.py
from __future__ import annotations

import uuid

import streamlit as st
from models.api_client import (
    approve_redteam_case,
    create_eval_dataset_from_stage3,
    create_eval_experiment,
    create_redteam_dataset,
    generate_redteam_cases,
    get_eval_experiment_status_checked,
    invalidate_session_cache,
    reject_redteam_case,
    run_eval_cases,
    run_eval_experiment,
    run_single_eval_case,
    score_eval_case,
    sync_redteam_case_to_eval,
)
from models.feedback import ApiError, show_api_error
from models.session_state import refresh_actions

_TERMINAL_EXPERIMENT_STATUSES = {"completed", "failed", "interrupted", "cancelled"}


def _status_store() -> dict:
    store = st.session_state.get("eval_experiment_status")
    if not isinstance(store, dict):
        store = {}
        st.session_state.eval_experiment_status = store
    return store


def _request_key(experiment_id: str) -> str:
    keys = st.session_state.get("eval_run_keys")
    if not isinstance(keys, dict):
        keys = {}
        st.session_state.eval_run_keys = keys
    key = keys.get(experiment_id)
    if not key:
        key = f"ui:{experiment_id}:{uuid.uuid4().hex}"
        keys[experiment_id] = key
    return key


def _remember_status(experiment_id: str, status: dict) -> None:
    _status_store()[experiment_id] = status
    failures = st.session_state.get("eval_status_failures")
    if isinstance(failures, dict):
        failures.pop(experiment_id, None)
    server_key = status.get("run_request_key")
    if server_key:
        keys = st.session_state.get("eval_run_keys")
        if not isinstance(keys, dict):
            keys = {}
            st.session_state.eval_run_keys = keys
        keys[experiment_id] = server_key
    mode = status.get("execution_mode")
    if mode:
        modes = st.session_state.get("eval_run_modes")
        if not isinstance(modes, dict):
            modes = {}
            st.session_state.eval_run_modes = modes
        modes[experiment_id] = mode


def refresh_experiment_status(experiment_id: str) -> dict | None:
    """单次查询实验状态；连续失败达到上限后停止自动轮询。"""
    ok, payload = get_eval_experiment_status_checked(st.session_state.session_id, experiment_id)
    failures = st.session_state.get("eval_status_failures")
    if not isinstance(failures, dict):
        failures = {}
        st.session_state.eval_status_failures = failures
    if ok and isinstance(payload, dict):
        failures.pop(experiment_id, None)
        _remember_status(experiment_id, payload)
        return payload

    failures[experiment_id] = int(failures.get(experiment_id, 0)) + 1
    current = dict(_status_store().get(experiment_id) or {})
    if failures[experiment_id] >= 5:
        current["status_error"] = "状态读取连续失败，已停止自动轮询；请稍后重试。"
        current.pop("status_warning", None)
    else:
        current["status_warning"] = f"状态读取失败（第 {failures[experiment_id]} 次），将自动重试。"
    _status_store()[experiment_id] = current
    return None


def run_all_cases(run_mode: str, target_config: dict | None = None) -> None:
    try:
        result = run_eval_cases(
            st.session_state.session_id, None, run_mode, target_config=target_config
        )
    except ApiError as exc:
        show_api_error(exc)
        return
    refresh_actions()
    st.success(f"已创建 {len(result.get('created_runs', []))} 次评测运行。")
    st.rerun()


def run_case(eval_id: str, run_mode: str, target_config: dict | None = None) -> None:
    try:
        run_single_eval_case(
            st.session_state.session_id, eval_id, run_mode, target_config=target_config
        )
    except ApiError as exc:
        show_api_error(exc)
        return
    refresh_actions()
    st.rerun()


def save_score(
    eval_id: str,
    human_score: int,
    human_comment: str,
    passed: bool | None,
    actual_output: str,
) -> None:
    try:
        score_eval_case(
            st.session_state.session_id,
            eval_id,
            human_score,
            human_comment,
            passed,
            actual_output,
        )
    except ApiError as exc:
        show_api_error(exc)
        return
    refresh_actions()
    st.rerun()


def create_dataset_from_stage3(dataset_name: str) -> None:
    try:
        dataset = create_eval_dataset_from_stage3(
            st.session_state.session_id,
            dataset_name,
            "由当前阶段三评测用例创建。",
        )
    except ApiError as exc:
        show_api_error(exc)
        return
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
    try:
        experiment = create_eval_experiment(
            st.session_state.session_id,
            dataset_id,
            experiment_name,
            run_mode,
            baseline_experiment_id,
            target_config=target_config,
        )
    except ApiError as exc:
        show_api_error(exc)
        return
    invalidate_session_cache(st.session_state.session_id)
    st.success(f"实验已创建：{experiment.get('experiment_id')}")
    st.rerun()


def run_experiment(
    experiment_id: str,
    dry_run_only: bool = True,
    run_mode: str = "",
) -> None:
    """只提交一次运行；状态由面板按需轮询，不在控制器里同步长等待。"""
    request_key = _request_key(experiment_id)
    actual_mode = (
        "dry_run" if dry_run_only and run_mode in {"llm_node", "target_http"} else run_mode
    )
    try:
        with st.spinner("正在提交实验..."):
            result = run_eval_experiment(
                st.session_state.session_id,
                experiment_id,
                dry_run_only=dry_run_only,
                background=not dry_run_only,
                idempotency_key=request_key,
            )
    except ApiError as exc:
        # 提交失败不得写入 accepted/running 等"已受理"状态。
        show_api_error(exc)
        return

    status_payload = result.get("status_payload")
    if isinstance(status_payload, dict):
        status = dict(status_payload)
        if actual_mode and not status.get("execution_mode"):
            status["execution_mode"] = actual_mode
        status.setdefault("run_request_key", request_key)
        _remember_status(experiment_id, status)
    elif isinstance(result.get("status"), str):
        status = {
            "experiment_id": experiment_id,
            "status": result.get("status"),
            "execution_mode": result.get("execution_mode") or actual_mode,
            "run_request_key": result.get("run_request_key") or request_key,
            "completed_cases": len(result.get("run_ids") or []),
            "total_cases": len(result.get("eval_ids") or []),
            "failed_cases": 0,
        }
        _remember_status(experiment_id, status)
        # 同步执行返回的字段不含 failed_cases；补一次 GET 让终态展示准确。
        refresh_experiment_status(experiment_id)
    elif result.get("accepted"):
        _remember_status(
            experiment_id,
            {
                "experiment_id": experiment_id,
                "status": "accepted",
                "execution_mode": actual_mode,
                "run_request_key": request_key,
            },
        )
    invalidate_session_cache(st.session_state.session_id)
    st.rerun()


def generate_redteam() -> None:
    try:
        created = generate_redteam_cases(st.session_state.session_id)
    except ApiError as exc:
        # 失败只提示一次，不显示"已生成 0 条"，也不刷新/rerun。
        show_api_error(exc)
        return
    st.success(f"已生成 {len(created)} 条红队用例草稿。")
    refresh_actions()
    st.rerun()


def create_redteam_dataset_and_refresh() -> None:
    try:
        dataset = create_redteam_dataset(st.session_state.session_id)
    except ApiError as exc:
        show_api_error(exc)
        return
    st.success(f"数据集已创建：{dataset.get('dataset_id')}")
    refresh_actions()
    st.rerun()


def approve_redteam(case_id: str) -> None:
    try:
        approve_redteam_case(st.session_state.session_id, case_id, "已在复核工作台批准")
    except ApiError as exc:
        show_api_error(exc)
        return
    refresh_actions()
    st.rerun()


def reject_redteam(case_id: str) -> None:
    try:
        reject_redteam_case(st.session_state.session_id, case_id, "已在复核工作台驳回")
    except ApiError as exc:
        show_api_error(exc)
        return
    refresh_actions()
    st.rerun()


def sync_redteam_case(case_id: str) -> None:
    try:
        eval_case = sync_redteam_case_to_eval(st.session_state.session_id, case_id)
    except ApiError as exc:
        show_api_error(exc)
        return
    st.success(f"已同步为评测用例：{eval_case.get('eval_id')}")
    refresh_actions()
    st.rerun()
