# frontend/models/api_client.py
from __future__ import annotations

import time

import requests
import streamlit as st

from models.auth import _auth_headers, _refresh_access_token
from models.config import API_BASE
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


def _cached_get(cache_key: str, path: str, ttl: float):
    """带 TTL 的只读 GET：命中直接返回；失败结果（None）不入缓存。"""
    store = st.session_state.get(_API_CACHE_KEY)
    if store is None:
        store = {}
        st.session_state[_API_CACHE_KEY] = store
    entry = store.get(cache_key)
    now = time.monotonic()
    if entry is not None and now - entry[0] < ttl:
        return entry[1]
    result = api_get(path)
    if result is not None:
        store[cache_key] = (now, result)
    return result


def invalidate_api_cache(prefix: str = "") -> None:
    """清空前端读取缓存；传 prefix 时只清匹配键。"""
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


def api_post(path: str, body: dict) -> dict | None:
    try:
        r = _http_session.post(f"{API_BASE}{path}", json=body, headers=_auth_headers(), timeout=120)
        if r.status_code == 401 and _refresh_access_token():
            r = _http_session.post(
                f"{API_BASE}{path}", json=body, headers=_auth_headers(), timeout=120
            )
        r.raise_for_status()
        return r.json()
    except requests.exceptions.Timeout:
        st.error("⏱️ 请求超时，模型响应较慢，请稍后重试。")
        return None
    except requests.exceptions.ConnectionError:
        st.error(f"🔌 无法连接到后端服务，请确认 API 已启动（当前 API_BASE：{API_BASE}）。")
        return None
    except requests.exceptions.HTTPError as e:
        detail = ""
        try:
            payload = e.response.json()
            detail = payload.get("detail", "") if isinstance(payload, dict) else ""
        except Exception:
            detail = ""
        st.error(f"❌ 请求失败（HTTP {e.response.status_code}），请稍后重试或联系管理员。")
        if detail:
            with st.expander("🔧 技术详情", expanded=False):
                st.caption(str(detail))
        return None
    except Exception:
        st.error("❌ 发生未知错误，请稍后重试或联系管理员。")
        return None


def api_get(path: str) -> dict | list | None:
    try:
        r = _http_session.get(f"{API_BASE}{path}", headers=_auth_headers(), timeout=30)
        if r.status_code == 401 and _refresh_access_token():
            r = _http_session.get(f"{API_BASE}{path}", headers=_auth_headers(), timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.Timeout:
        st.error("⏱️ 请求超时。")
        return None
    except requests.exceptions.ConnectionError:
        st.error("🔌 无法连接到后端服务。")
        return None
    except requests.exceptions.HTTPError as e:
        if e.response.status_code != 404:
            st.error(f"❌ 请求失败（HTTP {e.response.status_code}），请稍后重试。")
        return None
    except Exception:
        st.error("❌ 发生未知错误，请稍后重试或联系管理员。")
        return None


def api_patch(path: str, body: dict) -> dict | None:
    try:
        r = _http_session.patch(f"{API_BASE}{path}", json=body, headers=_auth_headers(), timeout=30)
        if r.status_code == 401 and _refresh_access_token():
            r = _http_session.patch(
                f"{API_BASE}{path}", json=body, headers=_auth_headers(), timeout=30
            )
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        status_code = e.response.status_code if e.response is not None else "连接"
        st.error(f"❌ 重命名失败（{status_code}）。")
        return None


def api_delete(path: str) -> dict | None:
    try:
        r = _http_session.delete(f"{API_BASE}{path}", headers=_auth_headers(), timeout=30)
        if r.status_code == 401 and _refresh_access_token():
            r = _http_session.delete(f"{API_BASE}{path}", headers=_auth_headers(), timeout=30)
        r.raise_for_status()
        try:
            return r.json()
        except ValueError:
            return {}
    except requests.exceptions.Timeout:
        st.error("⏱️ 请求超时。")
        return None
    except requests.exceptions.ConnectionError:
        st.error(f"🔌 无法连接到后端服务，请确认 API 已启动（当前 API_BASE：{API_BASE}）。")
        return None
    except requests.exceptions.HTTPError as e:
        detail = ""
        try:
            payload = e.response.json()
            detail = payload.get("detail", "") if isinstance(payload, dict) else ""
        except Exception:
            detail = ""
        st.error(f"❌ 删除失败（HTTP {e.response.status_code}）。")
        if detail:
            with st.expander("🔧 技术详情", expanded=False):
                st.caption(str(detail))
        return None
    except Exception:
        st.error("❌ 发生未知错误，请稍后重试或联系管理员。")
        return None


def get_health() -> dict:
    result = _cached_get("health", "/health", _HEALTH_TTL)
    return result if isinstance(result, dict) else {}


def create_session(scenario_id: str | None = None) -> dict | None:
    body: dict = {}
    if scenario_id:
        body["scenario_id"] = scenario_id
    result = api_post("/sessions/", body)
    if isinstance(result, dict):
        invalidate_api_cache("sessions:")
        return result
    return None


def list_builtin_scenarios() -> list[dict]:
    result = _cached_get("scenarios:list", "/sessions/scenarios", _STATIC_READ_TTL)
    return result if isinstance(result, list) else []


def get_builtin_scenario(scenario_id: str) -> dict | None:
    result = _cached_get(
        f"scenarios:{scenario_id}",
        f"/sessions/scenarios/{scenario_id}",
        _STATIC_READ_TTL,
    )
    return result if isinstance(result, dict) else None


def bootstrap_scenario_input(session_id: str, scenario_input: str) -> dict | None:
    return send_message(session_id, scenario_input)


def create_session_id_only(scenario_id: str | None = None) -> str | None:
    result = create_session(scenario_id)
    if result:
        return result["session_id"]
    return None


def send_message(
    session_id: str,
    user_input: str,
    materials: list[str] | None = None,
) -> dict | None:
    body: dict = {"user_input": user_input}
    if materials:
        body["user_materials"] = materials
    result = api_post(f"/chat/{session_id}", body)
    if result is not None:
        # 会话状态推进后，侧栏会话列表的 current_state / updated_at 已变化。
        invalidate_api_cache("sessions:")
    return result


def get_session(session_id: str) -> dict | None:
    return api_get(f"/sessions/{session_id}")


def recover_workflow(session_id: str, target_state: str, note: str = "") -> dict | None:
    """从 ERROR / RECOVERY_REQUIRED 显式恢复；失败返回 None 由视图层提示。"""
    result = api_post(
        f"/sessions/{session_id}/workflow/recover",
        {"target_state": target_state, "note": note},
    )
    if result is not None:
        invalidate_api_cache("sessions:")
        invalidate_session_cache(session_id)
    return result


def list_sessions() -> list[dict]:
    result = _cached_get("sessions:list", "/sessions/", _SESSION_LIST_TTL)
    return result if isinstance(result, list) else []


def get_governance_overview() -> dict | None:
    """治理总览聚合指标；30 秒 TTL，失败返回 None 交由视图层提示。"""
    result = _cached_get("governance:overview", "/governance/overview", _GOVERNANCE_TTL)
    return result if isinstance(result, dict) else None


def get_governance_gate_trends() -> list[dict] | None:
    result = _cached_get("governance:gate-trends", "/governance/gate-trends", _GOVERNANCE_TTL)
    return result if isinstance(result, list) else None


def get_governance_actions_backlog() -> list[dict] | None:
    result = _cached_get(
        "governance:actions-backlog", "/governance/actions-backlog", _GOVERNANCE_TTL
    )
    return result if isinstance(result, list) else None


def rename_session(session_id: str, name: str) -> dict | None:
    result = api_patch(f"/sessions/{session_id}/name", {"name": name})
    if result is not None:
        invalidate_api_cache("sessions:")
    return result


def export_report(session_id: str, format: str = "json") -> dict | None:
    return api_get(f"/sessions/{session_id}/export?format={format}")


def list_audit_events(session_id: str) -> list[dict]:
    result = _cached_get(
        _session_cache_key(session_id, "audit-events"),
        f"/sessions/{session_id}/audit-events",
        _SESSION_READ_TTL,
    )
    if isinstance(result, list):
        return result
    return []


def list_actions(session_id: str, status: str | None = "pending") -> list[dict]:
    path = f"/sessions/{session_id}/actions"
    if status:
        path += f"?status={status}"
    result = api_get(path)
    if isinstance(result, list):
        return result
    return []


def get_stage_readiness(session_id: str) -> dict:
    result = api_get(f"/sessions/{session_id}/stage-readiness")
    if isinstance(result, dict):
        return result
    return {}


def get_stage_resolution(session_id: str) -> dict:
    result = api_get(f"/sessions/{session_id}/stage-resolution")
    if isinstance(result, dict):
        return result
    return {}


def get_stage_advancement_decision(session_id: str, stage_id: int) -> dict:
    result = api_get(f"/sessions/{session_id}/stages/{stage_id}/advancement-decision")
    if isinstance(result, dict):
        return result
    return {}


def advance_stage_if_ready(session_id: str, stage_id: int) -> dict | None:
    result = api_post(
        f"/sessions/{session_id}/stages/{stage_id}/advance",
        {"reason": "frontend_stage_advance", "source": "api_advance"},
    )
    return apply_stage_operation_result(result)


def prepare_stage_operation(
    session_id: str, stage_id: int, operation: str, body: dict | None = None
) -> dict | None:
    result = api_post(f"/sessions/{session_id}/stages/{stage_id}/{operation}", body or {})
    return apply_stage_operation_result(result)


def list_interrupt_records(session_id: str) -> list[dict]:
    result = api_get(f"/sessions/{session_id}/interrupt-records")
    if isinstance(result, list):
        return result
    return []


def resolve_action(
    session_id: str,
    action_id: str,
    decision: str,
    note: str = "",
    payload_after: dict | None = None,
) -> bool:
    result = api_post(
        f"/sessions/{session_id}/actions/{action_id}/resolve",
        {"decision": decision, "note": note, "payload_after": payload_after},
    )
    if result:
        apply_stage_operation_result(result)
        st.session_state.interrupt_records = result.get("interrupt_records", [])
        st.session_state.current_state = result.get("current_state", st.session_state.current_state)
        st.session_state.pending_actions = [
            a for a in result.get("pending_actions", []) if a.get("status") == "pending"
        ]
    return result is not None


def resolve_flag(
    session_id: str,
    flag_id: str,
    action: str,
    note: str = "",
) -> bool:
    result = api_post(
        f"/sessions/{session_id}/flags/resolve",
        {"flag_id": flag_id, "action": action, "note": note},
    )
    apply_stage_operation_result(result)
    return result is not None


def list_evidence(session_id: str) -> list[dict]:
    result = _cached_get(
        _session_cache_key(session_id, "evidence"),
        f"/sessions/{session_id}/evidence",
        _SESSION_READ_TTL,
    )
    if isinstance(result, list):
        return result
    return []


def verify_evidence(session_id: str, evidence_id: str, note: str = "") -> bool:
    result = api_post(
        f"/sessions/{session_id}/evidence/{evidence_id}/verify",
        {"note": note},
    )
    apply_stage_operation_result(result)
    return result is not None


def list_safety_findings(session_id: str, status: str | None = "open") -> list[dict]:
    path = f"/sessions/{session_id}/safety-findings"
    if status:
        path += f"?status={status}"
    result = _cached_get(
        _session_cache_key(session_id, f"safety-findings:{status or 'all'}"),
        path,
        _SESSION_READ_TTL,
    )
    if isinstance(result, list):
        return result
    return []


def resolve_safety_finding(session_id: str, finding_id: str, status: str, note: str = "") -> bool:
    result = api_post(
        f"/sessions/{session_id}/safety-findings/{finding_id}/resolve",
        {"status": status, "note": note},
    )
    apply_stage_operation_result(result)
    return result is not None


def list_eval_cases(session_id: str) -> list[dict]:
    result = _cached_get(
        _session_cache_key(session_id, "eval-cases"),
        f"/sessions/{session_id}/eval-cases",
        _SESSION_READ_TTL,
    )
    if isinstance(result, list):
        return result
    return []


def list_eval_runs(session_id: str) -> list[dict]:
    result = _cached_get(
        _session_cache_key(session_id, "eval-runs"),
        f"/sessions/{session_id}/eval-runs",
        _SESSION_READ_TTL,
    )
    if isinstance(result, list):
        return result
    return []


def run_eval_cases(
    session_id: str,
    eval_ids: list[str] | None = None,
    run_mode: str = "manual",
    target_config: dict | None = None,
) -> dict | None:
    body: dict = {"eval_ids": eval_ids, "run_mode": run_mode}
    if target_config:
        body["target_config"] = target_config
    result = api_post(f"/sessions/{session_id}/eval-cases/run", body)
    return apply_stage_operation_result(result)


def run_single_eval_case(
    session_id: str,
    eval_id: str,
    run_mode: str = "manual",
    target_config: dict | None = None,
) -> dict | None:
    body: dict = {"eval_ids": [eval_id], "run_mode": run_mode}
    if target_config:
        body["target_config"] = target_config
    result = api_post(f"/sessions/{session_id}/eval-cases/{eval_id}/run", body)
    return apply_stage_operation_result(result)


def score_eval_case(
    session_id: str,
    eval_id: str,
    human_score: int | None,
    human_comment: str,
    passed: bool | None,
    actual_output: str | None = None,
) -> bool:
    result = api_post(
        f"/sessions/{session_id}/eval-cases/{eval_id}/score",
        {
            "human_score": human_score,
            "human_comment": human_comment,
            "passed": passed,
            "actual_output": actual_output,
        },
    )
    apply_stage_operation_result(result)
    return result is not None


def list_eval_datasets(session_id: str) -> list[dict]:
    result = _cached_get(
        _session_cache_key(session_id, "eval-datasets"),
        f"/sessions/{session_id}/eval-datasets",
        _SESSION_READ_TTL,
    )
    return result if isinstance(result, list) else []


def create_eval_dataset_from_stage3(
    session_id: str,
    name: str = "Stage 3 generated dataset",
    description: str = "",
) -> dict | None:
    result = api_post(
        f"/sessions/{session_id}/eval-datasets/from-stage3",
        {"name": name, "description": description, "version": "0.1", "owner": "system"},
    )
    return apply_stage_operation_result(result)


def list_eval_experiments(session_id: str) -> list[dict]:
    result = _cached_get(
        _session_cache_key(session_id, "eval-experiments"),
        f"/sessions/{session_id}/eval-experiments",
        _SESSION_READ_TTL,
    )
    return result if isinstance(result, list) else []


def list_redteam_cases(session_id: str) -> list[dict]:
    result = _cached_get(
        _session_cache_key(session_id, "redteam-cases"),
        f"/sessions/{session_id}/redteam/cases",
        _SESSION_READ_TTL,
    )
    return result if isinstance(result, list) else []


def get_redteam_coverage(session_id: str) -> dict:
    result = _cached_get(
        _session_cache_key(session_id, "redteam-coverage"),
        f"/sessions/{session_id}/redteam/coverage",
        _SESSION_READ_TTL,
    )
    return result if isinstance(result, dict) else {}


def generate_redteam_cases(session_id: str) -> list[dict]:
    result = api_post(f"/sessions/{session_id}/redteam/generate", {"stage": 3})
    return stage_operation_items(result)


def approve_redteam_case(session_id: str, case_id: str, note: str = "") -> dict | None:
    result = api_post(f"/sessions/{session_id}/redteam/cases/{case_id}/approve", {"note": note})
    return apply_stage_operation_result(result)


def reject_redteam_case(session_id: str, case_id: str, note: str = "") -> dict | None:
    result = api_post(f"/sessions/{session_id}/redteam/cases/{case_id}/reject", {"note": note})
    return apply_stage_operation_result(result)


def sync_redteam_case_to_eval(session_id: str, case_id: str) -> dict | None:
    result = api_post(f"/sessions/{session_id}/redteam/cases/{case_id}/to-eval-case", {})
    return apply_stage_operation_result(result)


def create_redteam_dataset(session_id: str) -> dict | None:
    result = api_post(
        f"/sessions/{session_id}/redteam/datasets",
        {"name": "Red Team generated dataset", "version": "0.1"},
    )
    return apply_stage_operation_result(result)


def create_eval_experiment(
    session_id: str,
    dataset_id: str,
    name: str,
    run_mode: str = "dry_run",
    baseline_experiment_id: str | None = None,
    target_config: dict | None = None,
) -> dict | None:
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
    result = api_post(f"/sessions/{session_id}/eval-experiments", body)
    return apply_stage_operation_result(result)


def run_eval_experiment(
    session_id: str, experiment_id: str, dry_run_only: bool = True
) -> dict | None:
    result = api_post(
        f"/sessions/{session_id}/eval-experiments/{experiment_id}/run",
        {"dry_run_only": dry_run_only},
    )
    return apply_stage_operation_result(result)


def create_report_artifact(session_id: str) -> dict | None:
    result = api_post(f"/sessions/{session_id}/reports", {})
    return apply_stage_operation_result(result)


def list_report_artifacts(session_id: str) -> list[dict]:
    result = _cached_get(
        _session_cache_key(session_id, "reports"),
        f"/sessions/{session_id}/reports",
        _SESSION_READ_TTL,
    )
    if isinstance(result, list):
        return result
    return []


def get_report_artifact(session_id: str, report_id: str) -> dict | None:
    # 报告快照是不可变版本化产物，内容不会原地变更，可长缓存避免每次 rerun 重下全文。
    return _cached_get(
        _session_cache_key(session_id, f"report:{report_id}"),
        f"/sessions/{session_id}/reports/{report_id}",
        _STATIC_READ_TTL,
    )


def list_risk_treatments(session_id: str) -> dict:
    result = api_get(f"/sessions/{session_id}/risk-treatments")
    return result if isinstance(result, dict) else {}


def upsert_risk_treatment(
    session_id: str,
    *,
    source_type: str,
    source_id: str,
    owner: str,
    mitigation_plan: str,
    status: str,
    note: str = "",
) -> dict | None:
    body = {
        "source_type": source_type,
        "source_id": source_id,
        "owner": owner,
        "mitigation_plan": mitigation_plan,
        "status": status,
        "note": note,
    }
    result = api_post(f"/sessions/{session_id}/risk-treatments", body)
    return apply_stage_operation_result(result)


def review_risk_treatment(
    session_id: str, treatment_id: str, decision: str, note: str = ""
) -> dict | None:
    result = api_post(
        f"/sessions/{session_id}/risk-treatments/{treatment_id}/review",
        {"decision": decision, "note": note},
    )
    return apply_stage_operation_result(result)


def get_approval_status(session_id: str) -> dict:
    result = api_get(f"/sessions/{session_id}/approval-status")
    return result if isinstance(result, dict) else {}


def list_project_approvals(session_id: str) -> list[dict]:
    result = api_get(f"/sessions/{session_id}/approvals")
    return result if isinstance(result, list) else []


def request_release_approval(session_id: str, decision: str, note: str = "") -> dict | None:
    result = api_post(
        f"/sessions/{session_id}/approvals/release",
        {"decision": decision, "note": note},
    )
    return result if isinstance(result, dict) else None


def add_materials_to_session(session_id: str, materials: list[str]) -> bool:
    result = api_post(
        f"/sessions/{session_id}/materials",
        {"materials": materials},
    )
    apply_stage_operation_result(result)
    return result is not None
