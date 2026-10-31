# frontend/models/api_client.py
from __future__ import annotations

import requests
import streamlit as st

from models.auth import _auth_headers, _refresh_access_token
from models.config import API_BASE
from models.stage_envelope import apply_stage_operation_result, stage_operation_items


def api_post(path: str, body: dict) -> dict | None:
    try:
        r = requests.post(f"{API_BASE}{path}", json=body, headers=_auth_headers(), timeout=120)
        if r.status_code == 401 and _refresh_access_token():
            r = requests.post(f"{API_BASE}{path}", json=body, headers=_auth_headers(), timeout=120)
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
        r = requests.get(f"{API_BASE}{path}", headers=_auth_headers(), timeout=30)
        if r.status_code == 401 and _refresh_access_token():
            r = requests.get(f"{API_BASE}{path}", headers=_auth_headers(), timeout=30)
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
        r = requests.patch(f"{API_BASE}{path}", json=body, headers=_auth_headers(), timeout=30)
        if r.status_code == 401 and _refresh_access_token():
            r = requests.patch(f"{API_BASE}{path}", json=body, headers=_auth_headers(), timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        status_code = e.response.status_code if e.response is not None else "连接"
        st.error(f"❌ 重命名失败（{status_code}）。")
        return None


def api_delete(path: str) -> dict | None:
    try:
        r = requests.delete(f"{API_BASE}{path}", headers=_auth_headers(), timeout=30)
        if r.status_code == 401 and _refresh_access_token():
            r = requests.delete(f"{API_BASE}{path}", headers=_auth_headers(), timeout=30)
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
    result = api_get("/health")
    return result if isinstance(result, dict) else {}


def create_session(scenario_id: str | None = None) -> dict | None:
    body: dict = {}
    if scenario_id:
        body["scenario_id"] = scenario_id
    result = api_post("/sessions/", body)
    return result if isinstance(result, dict) else None


def list_builtin_scenarios() -> list[dict]:
    result = api_get("/sessions/scenarios")
    return result if isinstance(result, list) else []


def get_builtin_scenario(scenario_id: str) -> dict | None:
    return api_get(f"/sessions/scenarios/{scenario_id}")


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
    return api_post(f"/chat/{session_id}", body)


def get_session(session_id: str) -> dict | None:
    return api_get(f"/sessions/{session_id}")


def list_sessions() -> list[dict]:
    result = api_get("/sessions/")
    if isinstance(result, list):
        return result
    return []


def rename_session(session_id: str, name: str) -> dict | None:
    return api_patch(f"/sessions/{session_id}/name", {"name": name})


def export_report(session_id: str, format: str = "json") -> dict | None:
    return api_get(f"/sessions/{session_id}/export?format={format}")


def list_audit_events(session_id: str) -> list[dict]:
    result = api_get(f"/sessions/{session_id}/audit-events")
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
    result = api_get(f"/sessions/{session_id}/evidence")
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
    result = api_get(path)
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
    result = api_get(f"/sessions/{session_id}/eval-cases")
    if isinstance(result, list):
        return result
    return []


def list_eval_runs(session_id: str) -> list[dict]:
    result = api_get(f"/sessions/{session_id}/eval-runs")
    if isinstance(result, list):
        return result
    return []


def run_eval_cases(
    session_id: str, eval_ids: list[str] | None = None, run_mode: str = "manual"
) -> dict | None:
    result = api_post(
        f"/sessions/{session_id}/eval-cases/run",
        {"eval_ids": eval_ids, "run_mode": run_mode},
    )
    return apply_stage_operation_result(result)


def run_single_eval_case(session_id: str, eval_id: str, run_mode: str = "manual") -> dict | None:
    result = api_post(
        f"/sessions/{session_id}/eval-cases/{eval_id}/run",
        {"eval_ids": [eval_id], "run_mode": run_mode},
    )
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
    result = api_get(f"/sessions/{session_id}/eval-datasets")
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
    result = api_get(f"/sessions/{session_id}/eval-experiments")
    return result if isinstance(result, list) else []


def list_redteam_cases(session_id: str) -> list[dict]:
    result = api_get(f"/sessions/{session_id}/redteam/cases")
    return result if isinstance(result, list) else []


def get_redteam_coverage(session_id: str) -> dict:
    result = api_get(f"/sessions/{session_id}/redteam/coverage")
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
) -> dict | None:
    result = api_post(
        f"/sessions/{session_id}/eval-experiments",
        {
            "dataset_id": dataset_id,
            "name": name,
            "description": "由复核工作台创建。",
            "run_mode": run_mode,
            "baseline_experiment_id": baseline_experiment_id,
            "run_config": {"runtime_validation": "deferred_by_instruction"},
        },
    )
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
    result = api_get(f"/sessions/{session_id}/reports")
    if isinstance(result, list):
        return result
    return []


def get_report_artifact(session_id: str, report_id: str) -> dict | None:
    return api_get(f"/sessions/{session_id}/reports/{report_id}")


def add_materials_to_session(session_id: str, materials: list[str]) -> bool:
    result = api_post(
        f"/sessions/{session_id}/materials",
        {"materials": materials},
    )
    apply_stage_operation_result(result)
    return result is not None
