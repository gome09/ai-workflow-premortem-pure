# frontend/models/api_client.py
from __future__ import annotations

import time
from dataclasses import dataclass

import requests
import streamlit as st

from models.auth import _auth_headers, _refresh_access_token
from models.config import API_BASE
from models.feedback import ApiError
from models.stage_envelope import apply_stage_operation_result, stage_operation_items

# 模块级共享 HTTP 连接池：一次页面渲染内会发起多次后端调用，复用同一 TCP
# 连接（keep-alive），避免每次 api_* 调用都新建连接。
_http_session = requests.Session()
_http_adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=20)
_http_session.mount("http://", _http_adapter)
_http_session.mount("https://", _http_adapter)

# 会话级读取缓存：存放在 st.session_state，天然按浏览器会话（=租户）隔离，
# 不使用 st.cache_data 的进程级全局缓存。
_API_CACHE_KEY = "_api_cache"
_HEALTH_TTL = 30.0
_STATIC_READ_TTL = 600.0
_SESSION_LIST_TTL = 10.0
_SESSION_READ_TTL = 5.0
_GOVERNANCE_TTL = 30.0


@dataclass
class _HttpOutcome:
    """单次 HTTP 尝试的结构化结果，供传输层统一转换为 ApiError。"""

    ok: bool
    payload: object = None
    status_code: int = 0
    error_kind: str = (
        ""  # timeout | connection | http | invalid_response | unknown | auth_transient
    )
    detail: object = None
    error_code: str = ""
    retryable: bool | None = None
    recovery_endpoint: str = ""


def _perform(
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
    timeout: float,
    allow_404: bool = False,
) -> _HttpOutcome:
    """执行一次请求；认证终态由公共层处理，业务失败交给调用方展示。"""

    def _send():
        kwargs: dict = {"headers": _auth_headers(), "timeout": timeout}
        if json_body is not None:
            kwargs["json"] = json_body
        return getattr(_http_session, method)(f"{API_BASE}{path}", **kwargs)

    try:
        r = _send()
        if r.status_code == 401:
            refresh = _refresh_access_token()
            if refresh == "ok":
                r = _send()
            elif refresh == "rejected":
                _expire_login_state()
                st.rerun()
            else:
                return _HttpOutcome(False, error_kind="auth_transient")
        if allow_404 and r.status_code == 404:
            return _HttpOutcome(False, status_code=404, error_kind="not_found")
        if r.status_code >= 400:
            detail: object = None
            error_code = ""
            retryable: bool | None = None
            recovery_endpoint = ""
            try:
                payload = r.json()
            except ValueError:
                payload = None
            if isinstance(payload, dict):
                detail = payload.get("detail")
                error_code = str(payload.get("error_code") or "")
                if isinstance(payload.get("retryable"), bool):
                    retryable = payload["retryable"]
                recovery_endpoint = str(payload.get("recovery_endpoint") or "")
                if isinstance(detail, dict):
                    error_code = error_code or str(detail.get("error_code") or "")
                    recovery_endpoint = recovery_endpoint or str(
                        detail.get("recovery_endpoint") or ""
                    )
                    if retryable is None and isinstance(detail.get("retryable"), bool):
                        retryable = detail["retryable"]
            return _HttpOutcome(
                False,
                status_code=r.status_code,
                error_kind="http",
                detail=detail,
                error_code=error_code,
                retryable=retryable,
                recovery_endpoint=recovery_endpoint,
            )
        if r.status_code == 204:
            return _HttpOutcome(True, payload={}, status_code=204)
        try:
            payload = r.json()
        except ValueError:
            return _HttpOutcome(False, status_code=r.status_code, error_kind="invalid_response")
        return _HttpOutcome(True, payload=payload, status_code=r.status_code)
    except requests.exceptions.Timeout:
        return _HttpOutcome(False, error_kind="timeout")
    except requests.exceptions.ConnectionError:
        return _HttpOutcome(False, error_kind="connection")
    except Exception:
        return _HttpOutcome(False, error_kind="unknown")


def _expire_login_state() -> None:
    """认证明确失效：清空凭证、缓存与会话数据，回到登录页。"""
    for key in ("access_token", "refresh_token", "user_role"):
        st.session_state.pop(key, None)
    invalidate_api_cache()
    for key in (
        "eval_run_keys",
        "eval_run_modes",
        "eval_experiment_status",
        "session_extra_pages",
        "chat_retry_draft",
        "_flash",
    ):
        st.session_state.pop(key, None)
    # 局部导入避免 models.session_state -> api_client 的模块级循环依赖。
    from models.session_state import _reset_session_state

    _reset_session_state()
    st.session_state.auth_notice = "登录已失效，请重新登录。"


def _request(
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
    timeout: float = 30,
    allow_404: bool = False,
) -> object:
    """执行请求并返回 payload；任何失败都以 ApiError 抛出，不渲染提示。"""
    outcome = _perform(method, path, json_body=json_body, timeout=timeout, allow_404=allow_404)
    if outcome.ok:
        return outcome.payload
    if outcome.error_kind == "not_found":
        return None
    raise ApiError(
        outcome.error_kind or "unknown",
        status_code=outcome.status_code,
        detail=outcome.detail,
        error_code=outcome.error_code,
        retryable=outcome.retryable,
        recovery_endpoint=outcome.recovery_endpoint,
    )


def _get_checked(path: str, *, timeout: float = 30, allow_404: bool = False) -> tuple[bool, object]:
    """GET 并保留失败信息；成功空集合仍返回 (True, [])/（True, {}）。完全静默。"""
    outcome = _perform("get", path, timeout=timeout, allow_404=allow_404)
    if outcome.ok:
        return True, outcome.payload
    return False, None


def _cached_get_checked(cache_key: str, path: str, ttl: float) -> tuple[bool, object]:
    """带 TTL 的 checked 只读 GET：只缓存成功结果，失败不写缓存。"""
    store = st.session_state.get(_API_CACHE_KEY)
    if store is None:
        store = {}
        st.session_state[_API_CACHE_KEY] = store
    entry = store.get(cache_key)
    now = time.monotonic()
    if entry is not None and now - entry[0] < ttl:
        return True, entry[1]
    ok, result = _get_checked(path)
    if ok:
        store[cache_key] = (now, result)
    return ok, result


def _cached_request(cache_key: str, path: str, ttl: float) -> object:
    """带 TTL 的 strict 只读 GET：命中直接返回；失败抛 ApiError 且不写缓存。"""
    store = st.session_state.get(_API_CACHE_KEY)
    if store is None:
        store = {}
        st.session_state[_API_CACHE_KEY] = store
    entry = store.get(cache_key)
    now = time.monotonic()
    if entry is not None and now - entry[0] < ttl:
        return entry[1]
    result = _request("get", path, timeout=30)
    store[cache_key] = (now, result)
    return result


def _expect_dict(payload: object) -> dict:
    if isinstance(payload, dict):
        return payload
    raise ApiError("invalid_response", status_code=200)


def _expect_list(payload: object) -> list:
    if isinstance(payload, list):
        return payload
    raise ApiError("invalid_response", status_code=200)


def invalidate_api_cache(prefix: str = "") -> None:
    """清空前端读取缓存；传 prefix 时只清匹配键。"""
    if prefix in {"", "sessions:"} or prefix.startswith("sessions:list"):
        st.session_state["session_pages_stale"] = True
    store = st.session_state.get(_API_CACHE_KEY)
    if not store:
        return
    if not prefix:
        store.clear()
        return
    for key in [k for k in store if k.startswith(prefix)]:
        del store[key]


def invalidate_session_cache(session_id: str) -> None:
    """清空某个会话的只读面板缓存（证据/安全/红队/评测/审计/报告）。"""
    if session_id:
        invalidate_api_cache(f"session:{session_id}:")


def _session_cache_key(session_id: str, name: str) -> str:
    return f"session:{session_id}:{name}"


def api_post(path: str, body: dict) -> dict:
    return _request("post", path, json_body=body, timeout=120)  # type: ignore[return-value]


def api_get(path: str) -> dict | list:
    return _request("get", path, timeout=30)  # type: ignore[return-value]


def api_patch(path: str, body: dict) -> dict:
    return _request("patch", path, json_body=body, timeout=30)  # type: ignore[return-value]


def api_put(path: str, body: dict) -> dict:
    return _request("put", path, json_body=body, timeout=30)  # type: ignore[return-value]


def api_delete(path: str) -> dict:
    payload = _request("delete", path, timeout=30)
    return payload if isinstance(payload, dict) else {}


def get_health() -> dict:
    return _expect_dict(_cached_request("health", "/health", _HEALTH_TTL))


def create_session(scenario_id: str | None = None) -> dict:
    body: dict = {}
    if scenario_id:
        body["scenario_id"] = scenario_id
    result = _expect_dict(api_post("/sessions/", body))
    invalidate_api_cache("sessions:")
    return result


def list_builtin_scenarios() -> list[dict]:
    return _expect_list(_cached_request("scenarios:list", "/sessions/scenarios", _STATIC_READ_TTL))


def get_builtin_scenario(scenario_id: str) -> dict:
    return _expect_dict(
        _cached_request(
            f"scenarios:{scenario_id}",
            f"/sessions/scenarios/{scenario_id}",
            _STATIC_READ_TTL,
        )
    )


def bootstrap_scenario_input(session_id: str, scenario_input: str) -> dict:
    return send_message(session_id, scenario_input)


def create_session_id_only(scenario_id: str | None = None) -> str:
    return create_session(scenario_id)["session_id"]


def send_message(
    session_id: str,
    user_input: str,
    materials: list[str] | None = None,
) -> dict:
    body: dict = {"user_input": user_input}
    if materials:
        body["user_materials"] = materials
    result = _expect_dict(api_post(f"/chat/{session_id}", body))
    # 会话状态推进后，侧栏会话列表的 current_state / updated_at 已变化。
    invalidate_api_cache("sessions:")
    return result


def get_session_checked(session_id: str) -> tuple[bool, object]:
    return _get_checked(f"/sessions/{session_id}")


def recover_workflow(session_id: str, target_state: str, note: str = "") -> dict:
    """从 ERROR / RECOVERY_REQUIRED 显式恢复；失败抛 ApiError 由 controller 提示。"""
    result = _expect_dict(
        api_post(
            f"/sessions/{session_id}/workflow/recover",
            {"target_state": target_state, "note": note},
        )
    )
    invalidate_api_cache("sessions:")
    invalidate_session_cache(session_id)
    return result


def list_sessions_checked(limit: int = 20, offset: int = 0) -> tuple[bool, object]:
    path = f"/sessions/?limit={limit}&offset={offset}"
    return _cached_get_checked(f"sessions:list:{limit}:{offset}", path, _SESSION_LIST_TTL)


def get_governance_overview() -> dict:
    """治理总览聚合指标；30 秒 TTL，失败抛 ApiError 交由视图层提示。"""
    return _expect_dict(
        _cached_request("governance:overview", "/governance/overview", _GOVERNANCE_TTL)
    )


def get_governance_gate_trends() -> list[dict]:
    return _expect_list(
        _cached_request("governance:gate-trends", "/governance/gate-trends", _GOVERNANCE_TTL)
    )


def get_governance_actions_backlog() -> list[dict]:
    return _expect_list(
        _cached_request(
            "governance:actions-backlog", "/governance/actions-backlog", _GOVERNANCE_TTL
        )
    )


def rename_session(session_id: str, name: str) -> dict:
    result = _expect_dict(api_patch(f"/sessions/{session_id}/name", {"name": name}))
    invalidate_api_cache("sessions:")
    return result


def export_report(session_id: str, format: str = "json") -> dict:
    return _expect_dict(api_get(f"/sessions/{session_id}/export?format={format}"))


def list_audit_events(session_id: str) -> list[dict]:
    return _expect_list(
        _cached_request(
            _session_cache_key(session_id, "audit-events"),
            f"/sessions/{session_id}/audit-events",
            _SESSION_READ_TTL,
        )
    )


def list_actions_checked(session_id: str, status: str | None = "pending") -> tuple[bool, object]:
    path = f"/sessions/{session_id}/actions"
    if status:
        path += f"?status={status}"
    return _get_checked(path)


def get_stage_readiness_checked(session_id: str) -> tuple[bool, object]:
    return _get_checked(f"/sessions/{session_id}/stage-readiness")


def get_stage_resolution_checked(session_id: str) -> tuple[bool, object]:
    return _get_checked(f"/sessions/{session_id}/stage-resolution")


def get_stage_advancement_decision_checked(session_id: str, stage_id: int) -> tuple[bool, object]:
    return _get_checked(f"/sessions/{session_id}/stages/{stage_id}/advancement-decision")


def advance_stage_if_ready(session_id: str, stage_id: int) -> dict:
    result = _expect_dict(
        api_post(
            f"/sessions/{session_id}/stages/{stage_id}/advance",
            {"reason": "frontend_stage_advance", "source": "api_advance"},
        )
    )
    return apply_stage_operation_result(result) or result


def prepare_stage_operation(
    session_id: str, stage_id: int, operation: str, body: dict | None = None
) -> dict:
    result = _expect_dict(
        api_post(f"/sessions/{session_id}/stages/{stage_id}/{operation}", body or {})
    )
    return apply_stage_operation_result(result) or result


def list_interrupt_records_checked(session_id: str) -> tuple[bool, object]:
    return _get_checked(f"/sessions/{session_id}/interrupt-records")


def resolve_action(
    session_id: str,
    action_id: str,
    decision: str,
    note: str = "",
    payload_after: dict | None = None,
) -> None:
    result = _expect_dict(
        api_post(
            f"/sessions/{session_id}/actions/{action_id}/resolve",
            {"decision": decision, "note": note, "payload_after": payload_after},
        )
    )
    apply_stage_operation_result(result)
    st.session_state.interrupt_records = result.get("interrupt_records", [])
    st.session_state.current_state = result.get("current_state", st.session_state.current_state)
    st.session_state.pending_actions = [
        a for a in result.get("pending_actions", []) if a.get("status") == "pending"
    ]


def resolve_flag(
    session_id: str,
    flag_id: str,
    action: str,
    note: str = "",
) -> None:
    result = _expect_dict(
        api_post(
            f"/sessions/{session_id}/flags/resolve",
            {"flag_id": flag_id, "action": action, "note": note},
        )
    )
    apply_stage_operation_result(result)


def list_evidence(session_id: str) -> list[dict]:
    return _expect_list(
        _cached_request(
            _session_cache_key(session_id, "evidence"),
            f"/sessions/{session_id}/evidence",
            _SESSION_READ_TTL,
        )
    )


def verify_evidence(session_id: str, evidence_id: str, note: str = "") -> None:
    result = _expect_dict(
        api_post(
            f"/sessions/{session_id}/evidence/{evidence_id}/verify",
            {"note": note},
        )
    )
    apply_stage_operation_result(result)


def list_safety_findings(session_id: str, status: str | None = "open") -> list[dict]:
    path = f"/sessions/{session_id}/safety-findings"
    if status:
        path += f"?status={status}"
    return _expect_list(
        _cached_request(
            _session_cache_key(session_id, f"safety-findings:{status or 'all'}"),
            path,
            _SESSION_READ_TTL,
        )
    )


def resolve_safety_finding(session_id: str, finding_id: str, status: str, note: str = "") -> None:
    result = _expect_dict(
        api_post(
            f"/sessions/{session_id}/safety-findings/{finding_id}/resolve",
            {"status": status, "note": note},
        )
    )
    apply_stage_operation_result(result)


def list_eval_cases(session_id: str) -> list[dict]:
    return _expect_list(
        _cached_request(
            _session_cache_key(session_id, "eval-cases"),
            f"/sessions/{session_id}/eval-cases",
            _SESSION_READ_TTL,
        )
    )


def list_eval_runs_checked(session_id: str) -> tuple[bool, object]:
    return _cached_get_checked(
        _session_cache_key(session_id, "eval-runs"),
        f"/sessions/{session_id}/eval-runs",
        _SESSION_READ_TTL,
    )


def run_eval_cases(
    session_id: str,
    eval_ids: list[str] | None = None,
    run_mode: str = "manual",
    target_config: dict | None = None,
) -> dict:
    body: dict = {"eval_ids": eval_ids, "run_mode": run_mode}
    if target_config:
        body["target_config"] = target_config
    result = _expect_dict(api_post(f"/sessions/{session_id}/eval-cases/run", body))
    return apply_stage_operation_result(result) or result


def run_single_eval_case(
    session_id: str,
    eval_id: str,
    run_mode: str = "manual",
    target_config: dict | None = None,
) -> dict:
    body: dict = {"eval_ids": [eval_id], "run_mode": run_mode}
    if target_config:
        body["target_config"] = target_config
    result = _expect_dict(api_post(f"/sessions/{session_id}/eval-cases/{eval_id}/run", body))
    return apply_stage_operation_result(result) or result


def score_eval_case(
    session_id: str,
    eval_id: str,
    human_score: int | None,
    human_comment: str,
    passed: bool | None,
    actual_output: str | None = None,
) -> None:
    result = _expect_dict(
        api_post(
            f"/sessions/{session_id}/eval-cases/{eval_id}/score",
            {
                "human_score": human_score,
                "human_comment": human_comment,
                "passed": passed,
                "actual_output": actual_output,
            },
        )
    )
    apply_stage_operation_result(result)


def list_eval_datasets(session_id: str) -> list[dict]:
    return _expect_list(
        _cached_request(
            _session_cache_key(session_id, "eval-datasets"),
            f"/sessions/{session_id}/eval-datasets",
            _SESSION_READ_TTL,
        )
    )


def create_eval_dataset_from_stage3(
    session_id: str,
    name: str = "Stage 3 generated dataset",
    description: str = "",
) -> dict:
    result = _expect_dict(
        api_post(
            f"/sessions/{session_id}/eval-datasets/from-stage3",
            {"name": name, "description": description, "version": "0.1", "owner": "system"},
        )
    )
    return apply_stage_operation_result(result) or result


def list_eval_experiments(session_id: str) -> list[dict]:
    return _expect_list(
        _cached_request(
            _session_cache_key(session_id, "eval-experiments"),
            f"/sessions/{session_id}/eval-experiments",
            _SESSION_READ_TTL,
        )
    )


def list_redteam_cases(session_id: str) -> list[dict]:
    return _expect_list(
        _cached_request(
            _session_cache_key(session_id, "redteam-cases"),
            f"/sessions/{session_id}/redteam/cases",
            _SESSION_READ_TTL,
        )
    )


def get_redteam_coverage(session_id: str) -> dict:
    return _expect_dict(
        _cached_request(
            _session_cache_key(session_id, "redteam-coverage"),
            f"/sessions/{session_id}/redteam/coverage",
            _SESSION_READ_TTL,
        )
    )


def generate_redteam_cases(session_id: str) -> list[dict]:
    result = _expect_dict(api_post(f"/sessions/{session_id}/redteam/generate", {"stage": 3}))
    items = stage_operation_items(result)
    return items if items is not None else []


def approve_redteam_case(session_id: str, case_id: str, note: str = "") -> dict:
    result = _expect_dict(
        api_post(f"/sessions/{session_id}/redteam/cases/{case_id}/approve", {"note": note})
    )
    return apply_stage_operation_result(result) or result


def reject_redteam_case(session_id: str, case_id: str, note: str = "") -> dict:
    result = _expect_dict(
        api_post(f"/sessions/{session_id}/redteam/cases/{case_id}/reject", {"note": note})
    )
    return apply_stage_operation_result(result) or result


def sync_redteam_case_to_eval(session_id: str, case_id: str) -> dict:
    result = _expect_dict(
        api_post(f"/sessions/{session_id}/redteam/cases/{case_id}/to-eval-case", {})
    )
    return apply_stage_operation_result(result) or result


def create_redteam_dataset(session_id: str) -> dict:
    result = _expect_dict(
        api_post(
            f"/sessions/{session_id}/redteam/datasets",
            {"name": "Red Team generated dataset", "version": "0.1"},
        )
    )
    return apply_stage_operation_result(result) or result


def create_eval_experiment(
    session_id: str,
    dataset_id: str,
    name: str,
    run_mode: str = "dry_run",
    baseline_experiment_id: str | None = None,
    target_config: dict | None = None,
) -> dict:
    body: dict = {
        "dataset_id": dataset_id,
        "name": name,
        "description": "由复核工作台创建。",
        "run_mode": run_mode,
        "baseline_experiment_id": baseline_experiment_id,
        "run_config": {"runtime_validation": "deferred_by_instruction"},
    }
    if target_config:
        body["target_config"] = target_config
    result = _expect_dict(api_post(f"/sessions/{session_id}/eval-experiments", body))
    return apply_stage_operation_result(result) or result


def run_eval_experiment(
    session_id: str,
    experiment_id: str,
    dry_run_only: bool = True,
    background: bool | None = None,
    idempotency_key: str = "",
    timeout_seconds: int | None = None,
) -> dict:
    body: dict = {
        "dry_run_only": dry_run_only,
        "background": background,
        "idempotency_key": idempotency_key,
    }
    if timeout_seconds is not None:
        body["timeout_seconds"] = timeout_seconds
    result = _expect_dict(
        api_post(
            f"/sessions/{session_id}/eval-experiments/{experiment_id}/run",
            body,
        )
    )
    return apply_stage_operation_result(result) or result


def get_eval_experiment_status_checked(session_id: str, experiment_id: str) -> tuple[bool, object]:
    return _get_checked(f"/sessions/{session_id}/eval-experiments/{experiment_id}/status")


def create_report_artifact(session_id: str) -> dict:
    result = _expect_dict(api_post(f"/sessions/{session_id}/reports", {}))
    return apply_stage_operation_result(result) or result


def list_report_artifacts_checked(session_id: str) -> tuple[bool, object]:
    return _cached_get_checked(
        _session_cache_key(session_id, "reports"),
        f"/sessions/{session_id}/reports",
        _SESSION_READ_TTL,
    )


def get_report_artifact(session_id: str, report_id: str) -> dict:
    # 报告快照是不可变版本化产物，内容不会原地变更，可长缓存避免每次 rerun 重下全文。
    return _expect_dict(
        _cached_request(
            _session_cache_key(session_id, f"report:{report_id}"),
            f"/sessions/{session_id}/reports/{report_id}",
            _STATIC_READ_TTL,
        )
    )


def list_risk_treatments(session_id: str) -> dict:
    return _expect_dict(api_get(f"/sessions/{session_id}/risk-treatments"))


def upsert_risk_treatment(
    session_id: str,
    *,
    source_type: str,
    source_id: str,
    owner: str,
    mitigation_plan: str,
    status: str,
    note: str = "",
) -> dict:
    body = {
        "source_type": source_type,
        "source_id": source_id,
        "owner": owner,
        "mitigation_plan": mitigation_plan,
        "status": status,
        "note": note,
    }
    result = _expect_dict(api_post(f"/sessions/{session_id}/risk-treatments", body))
    invalidate_session_cache(session_id)
    return apply_stage_operation_result(result) or result


def review_risk_treatment(
    session_id: str, treatment_id: str, decision: str, note: str = ""
) -> dict:
    result = _expect_dict(
        api_post(
            f"/sessions/{session_id}/risk-treatments/{treatment_id}/review",
            {"decision": decision, "note": note},
        )
    )
    invalidate_session_cache(session_id)
    return apply_stage_operation_result(result) or result


def get_approval_status(session_id: str) -> dict:
    return _expect_dict(api_get(f"/sessions/{session_id}/approval-status"))


def request_release_approval(session_id: str, decision: str, note: str = "") -> dict:
    return _expect_dict(
        api_post(
            f"/sessions/{session_id}/approvals/release",
            {"decision": decision, "note": note},
        )
    )


def set_target_deployment(session_id: str, endpoint: str, version: str) -> dict:
    result = _expect_dict(
        api_put(
            f"/sessions/{session_id}/target-deployment",
            {"endpoint": endpoint, "version": version},
        )
    )
    invalidate_session_cache(session_id)
    return result


def list_human_calibrations(session_id: str, eval_run_id: str | None = None) -> list[dict]:
    path = f"/sessions/{session_id}/human-calibrations"
    if eval_run_id:
        path += f"?eval_run_id={eval_run_id}"
    return _expect_list(api_get(path))


def calibrate_eval_run(
    session_id: str,
    run_id: str,
    human_label: str,
    human_comment: str = "",
    disagreement_reason: str = "",
) -> dict:
    result = _expect_dict(
        api_post(
            f"/sessions/{session_id}/eval-runs/{run_id}/calibrate",
            {
                "human_label": human_label,
                "human_comment": human_comment,
                "disagreement_reason": disagreement_reason,
            },
        )
    )
    invalidate_session_cache(session_id)
    return result


def create_invitation(email: str, role: str = "viewer") -> dict:
    return _expect_dict(api_post("/auth/invitations", {"email": email, "role": role}))


def list_invitations() -> list[dict]:
    return _expect_list(api_get("/auth/invitations"))


def accept_invitation(token: str, password: str) -> dict:
    return _expect_dict(
        api_post(
            "/auth/invitations/accept",
            {"token": token, "password": password},
        )
    )


def add_materials_to_session(session_id: str, materials: list[str]) -> None:
    result = _expect_dict(
        api_post(
            f"/sessions/{session_id}/materials",
            {"materials": materials},
        )
    )
    apply_stage_operation_result(result)
