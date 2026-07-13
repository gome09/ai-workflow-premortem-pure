# frontend/app.py
from __future__ import annotations

import json
import os

import requests
import streamlit as st
from components.redteam_panel import render_redteam_panel
from components.report_panel import render_report_panel

# ─────────────────────────────────────────────────────────────────────────────
# 配置
# ─────────────────────────────────────────────────────────────────────────────

API_BASE = os.getenv("API_BASE", "http://localhost:8000")

st.set_page_config(
    page_title="AI Workflow Review Workbench",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────────────────────

STRUCTURED_EDIT_SOURCE_TYPES = {"parser", "policy_gap", "evidence_gap", "eval_coverage"}

# TODO: 这个文件太长了，应该把 sidebar 和 main area 拆成两个文件
# 但目前能跑就先不动了


def apply_stage_operation_result(result: dict | None) -> dict | None:
    """Consume the current StageOperationEnvelope shape in one place.

    Mutating operations return domain payloads plus
    stage_advancement_decision / next_required_operation. The frontend keeps the
    domain behavior but stores the canonical advancement view and invalidates
    cached readiness/resolution panels so the next render fetches fresh data.
    """
    if not isinstance(result, dict):
        return result

    decision = result.get("stage_advancement_decision")
    if isinstance(decision, dict):
        st.session_state.stage_advancement_decision = decision
        stage_id = decision.get("stage_id")
        if stage_id is not None:
            decisions = dict(st.session_state.get("stage_advancement_decisions", {}))
            decisions[str(stage_id)] = decision
            decisions[f"stage_{stage_id}"] = decision
            st.session_state.stage_advancement_decisions = decisions

    next_operation = result.get("next_required_operation")
    if next_operation is not None:
        st.session_state.next_required_operation = next_operation

    if result.get("current_state"):
        st.session_state.current_state = result.get("current_state")
    elif isinstance(decision, dict) and decision.get("current_state"):
        st.session_state.current_state = decision.get("current_state")

    if isinstance(result.get("interrupt_records"), list):
        st.session_state.interrupt_records = result.get("interrupt_records", [])
    if isinstance(result.get("pending_actions"), list):
        st.session_state.pending_actions = [
            action
            for action in result.get("pending_actions", [])
            if action.get("status") == "pending"
        ]

    st.session_state.stage_readiness = {}
    st.session_state.stage_resolution = {}
    return result


def stage_operation_items(result: dict | list | None) -> list[dict]:
    """Return list-style domain items while preserving StageOperationEnvelope state."""
    if isinstance(result, list):
        return result
    applied = apply_stage_operation_result(result if isinstance(result, dict) else None)
    if isinstance(applied, dict):
        for key in ("items", "result"):
            value = applied.get(key)
            if isinstance(value, list):
                return value
    return []


def api_post(path: str, body: dict) -> dict | None:
    try:
        r = requests.post(f"{API_BASE}{path}", json=body, timeout=120)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.Timeout:
        st.error("⏱️ 请求超时，模型响应较慢，请稍后重试。")
        return None
    except requests.exceptions.ConnectionError:
        st.error(f"🔌 无法连接到后端服务，请确认 API 已启动（当前 API_BASE：{API_BASE}）。")
        return None
    except requests.exceptions.HTTPError as e:
        st.error(f"❌ 请求失败：{e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        st.error(f"❌ 未知错误：{e}")
        return None


def api_get(path: str) -> dict | list | None:
    try:
        r = requests.get(f"{API_BASE}{path}", timeout=30)
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
            st.error(f"❌ 请求失败：{e.response.status_code}")
        return None
    except Exception as e:
        st.error(f"❌ 未知错误：{e}")
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
            "description": "Created from Streamlit Review Workbench.",
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


def restore_messages_from_ctx(ctx: dict) -> list[dict]:
    """
    从 API 返回的 ctx 中还原展示用的消息列表。
    过滤 system / tool 角色消息，按阶段顺序排列。
    """
    messages = []
    history = ctx.get("conversation_history", {})
    for stage_key in sorted(history.keys()):
        for msg in history[stage_key]:
            if msg["role"] in ("system", "tool"):
                continue
            messages.append(
                {
                    "role": msg["role"],
                    "content": msg["content"],
                    "metadata": msg.get("metadata", {}),
                }
            )
    return messages


# ─────────────────────────────────────────────────────────────────────────────
# 映射表
# ─────────────────────────────────────────────────────────────────────────────

STATE_LABELS: dict[str, tuple[str, str]] = {
    "init": ("🟡", "收集项目信息"),
    "s1_running": ("🔵", "阶段一：失败模式识别"),
    "s1_review": ("🟠", "阶段一：等待确认"),
    "s2_running": ("🔵", "阶段二：工作流设计"),
    "s2_review": ("🟠", "阶段二：等待确认"),
    "s3_running": ("🔵", "阶段三：压力测试"),
    "s3_review": ("🟠", "阶段三：等待确认"),
    "s4_running": ("🔵", "阶段四：触发方式"),
    "s4_review": ("🟠", "阶段四：等待确认"),
    "complete": ("✅", "全流程完成"),
}

STAGE_PROGRESS: dict[str, int] = {
    "init": 0,
    "s1_running": 15,
    "s1_review": 25,
    "s2_running": 40,
    "s2_review": 50,
    "s3_running": 65,
    "s3_review": 75,
    "s4_running": 88,
    "s4_review": 95,
    "complete": 100,
}

MODEL_LABELS: dict[str, str] = {
    "init": "DeepSeek V4 Flash",
    "s1_running": "DeepSeek V4 Pro 🧠",
    "s1_review": "等待确认",
    "s2_running": "DeepSeek V4 Flash",
    "s2_review": "等待确认",
    "s3_running": "DeepSeek V4 Pro 🧠",
    "s3_review": "等待确认",
    "s4_running": "DeepSeek V4 Flash",
    "s4_review": "等待确认",
    "complete": "已完成",
}

CHAT_PLACEHOLDER: dict[str, str] = {
    "init": "描述你想分析的 AI 模型和应用场景...",
    "s1_running": "补充说明或追问...",
    "s1_review": "输入「确认」继续，或描述你的修改意见...",
    "s2_running": "补充说明或追问...",
    "s2_review": "输入「确认」继续，或描述你的修改意见...",
    "s3_running": "补充说明或追问...",
    "s3_review": "输入「确认」继续，或描述你的修改意见...",
    "s4_running": "补充说明或追问...",
    "s4_review": "输入「确认」完成，或描述你的修改意见...",
    "complete": "全流程已完成，可从左侧导出报告。",
}

# ─────────────────────────────────────────────────────────────────────────────
# Session State 初始化
# ─────────────────────────────────────────────────────────────────────────────


def init_session_state() -> None:
    defaults = {
        "session_id": None,
        "selected_scenario_id": None,
        "selected_scenario_label": "[通用模式]",
        "messages": [],
        "current_state": "init",
        "pending_flags": [],
        "pending_actions": [],
        "interrupt_records": [],
        "stage_readiness": {},
        "stage_resolution": {},
        "stage_advancement_decision": {},
        "stage_advancement_decisions": {},
        "next_required_operation": None,
        "health": {},
        "is_loading": False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


init_session_state()

# ─────────────────────────────────────────────────────────────────────────────
# 辅助：刷新当前会话的 flags/actions
# ─────────────────────────────────────────────────────────────────────────────


def refresh_flags() -> None:
    if not st.session_state.session_id:
        return
    ctx = get_session(st.session_state.session_id)
    if ctx:
        st.session_state.pending_flags = [
            f for f in ctx.get("flagged_items", []) if f["status"] == "pending"
        ]
        st.session_state.pending_actions = [
            a for a in ctx.get("pending_actions", []) if a["status"] == "pending"
        ]


def refresh_actions() -> None:
    if not st.session_state.session_id:
        return
    st.session_state.pending_actions = list_actions(
        st.session_state.session_id,
        status="pending",
    )
    st.session_state.interrupt_records = list_interrupt_records(st.session_state.session_id)
    st.session_state.stage_readiness = get_stage_readiness(st.session_state.session_id)


def handle_send(user_input: str, materials: list[str] | None = None) -> None:
    """
    统一处理发送消息的逻辑：
    追加用户消息 → 调用 API → 追加 AI 回复 → 刷新状态
    """
    st.session_state.messages.append(
        {
            "role": "user",
            "content": user_input,
            "metadata": {},
        }
    )

    with st.spinner("🤖 AI 思考中，请稍候..."):
        result = send_message(
            session_id=st.session_state.session_id,
            user_input=user_input,
            materials=materials,
        )

    if result:
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": result["ai_reply"],
                "metadata": {},
            }
        )
        st.session_state.current_state = result["current_state"]
        refresh_flags()
        refresh_actions()


# ─────────────────────────────────────────────────────────────────────────────
# 左侧边栏
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🔬 AI 工作流工具")
    st.caption("项目立项失败模式分析")
    st.session_state.health = get_health()
    if st.session_state.health:
        st.caption(
            "Execution: "
            f"`{st.session_state.health.get('workflow_execution_mode', 'unknown')}` · "
            f"{st.session_state.health.get('interrupt_adapter_status', 'unknown')}"
        )
    st.divider()

    # ── 会话管理 ──────────────────────────────────────────────────────────────
    st.subheader("📋 会话管理")

    col_new, col_refresh = st.columns(2)

    with col_new:
        scenarios = list_builtin_scenarios()
        scenario_options = {"[通用模式]": None}
        for item in scenarios:
            scenario_options[f"{item.get('name')} · {item.get('scenario_id')}"] = item.get(
                "scenario_id"
            )

        selected_scenario_label = st.selectbox(
            "内置场景",
            options=list(scenario_options.keys()),
            key="selected_scenario_label",
        )
        selected_scenario_id = scenario_options[selected_scenario_label]

        if selected_scenario_id:
            scenario_detail = get_builtin_scenario(selected_scenario_id)
            if scenario_detail:
                st.caption(scenario_detail.get("description", ""))
                st.caption(
                    f"profile=`{scenario_detail.get('domain_profile')}` · mock=`{scenario_detail.get('mock_fixture')}`"
                )
                with st.expander("查看场景样例输入", expanded=False):
                    st.code(scenario_detail.get("input_sample", ""), language="markdown")
        else:
            scenario_detail = None

        if st.button("➕ 新建会话", use_container_width=True):
            with st.spinner("创建中..."):
                created = create_session(selected_scenario_id)
            if created:
                sid = created["session_id"]
                st.session_state.session_id = sid
                st.session_state.selected_scenario_id = created.get("selected_scenario_id")
                st.session_state.messages = []
                st.session_state.current_state = "init"
                st.session_state.pending_flags = []
                st.session_state.pending_actions = []
                st.session_state.interrupt_records = []
                st.session_state.stage_readiness = {}

                bootstrap_input = (
                    scenario_detail.get("input_sample")
                    if scenario_detail
                    and scenario_detail.get("default_config", {}).get("auto_bootstrap_input")
                    else "你好，我想开始一个新的项目分析。"
                )
                with st.spinner("加载引导语..."):
                    result = bootstrap_scenario_input(sid, bootstrap_input)
                if result:
                    st.session_state.messages.append(
                        {
                            "role": "user",
                            "content": bootstrap_input,
                            "metadata": {},
                        }
                    )
                    st.session_state.messages.append(
                        {
                            "role": "assistant",
                            "content": result["ai_reply"],
                            "metadata": {},
                        }
                    )
                    st.session_state.current_state = result["current_state"]
                st.rerun()

    with col_refresh:
        if st.button("🔄 刷新", use_container_width=True):
            st.rerun()

    # ── 历史会话列表 ──────────────────────────────────────────────────────────
    sessions = list_sessions()
    if sessions:
        st.caption(f"最近 {len(sessions)} 个会话")
        for s in sessions[:10]:
            icon, _ = STATE_LABELS.get(s["current_state"], ("⚪", ""))
            raw_label = s.get("research_target") or "未命名"
            domain = s.get("domain") or ""

            # 截断过长的标签
            label_short = raw_label[:10] + "…" if len(raw_label) > 10 else raw_label
            domain_short = f" · {domain[:6]}" if domain else ""
            btn_label = f"{icon} {label_short}{domain_short}"

            # 高亮当前会话
            is_current = s["session_id"] == st.session_state.session_id
            btn_type = "primary" if is_current else "secondary"

            if st.button(
                btn_label,
                key=f"sess_{s['session_id']}",
                use_container_width=True,
                type=btn_type,
            ):
                if not is_current:
                    st.session_state.session_id = s["session_id"]
                    st.session_state.current_state = s["current_state"]

                    ctx = get_session(s["session_id"])
                    if ctx:
                        st.session_state.selected_scenario_id = ctx.get("selected_scenario_id")
                        st.session_state.messages = restore_messages_from_ctx(ctx)
                        st.session_state.pending_flags = [
                            f for f in ctx.get("flagged_items", []) if f["status"] == "pending"
                        ]
                        st.session_state.pending_actions = [
                            a for a in ctx.get("pending_actions", []) if a["status"] == "pending"
                        ]
                        st.session_state.interrupt_records = list_interrupt_records(s["session_id"])
                        st.session_state.stage_readiness = get_stage_readiness(s["session_id"])
                    st.rerun()
    else:
        st.caption("暂无历史会话")

    st.divider()

    # ── 当前进度 ──────────────────────────────────────────────────────────────
    if st.session_state.session_id:
        st.subheader("📊 当前进度")
        if st.session_state.selected_scenario_id:
            st.caption(f"当前场景：`{st.session_state.selected_scenario_id}`")

        state = st.session_state.current_state
        icon, label = STATE_LABELS.get(state, ("⚪", "未知"))
        progress = STAGE_PROGRESS.get(state, 0)
        model = MODEL_LABELS.get(state, "")

        st.markdown(f"**{icon} {label}**")
        st.progress(progress / 100)
        st.caption(f"进度 {progress}%　·　{model}")

        # 四个阶段的状态指示
        stage_cols = st.columns(4)
        stage_defs = [
            ("一", ["s1_running", "s1_review"]),
            ("二", ["s2_running", "s2_review"]),
            ("三", ["s3_running", "s3_review"]),
            ("四", ["s4_running", "s4_review"]),
        ]
        for i, (name, stage_states) in enumerate(stage_defs):
            with stage_cols[i]:
                current_progress = STAGE_PROGRESS.get(state, 0)
                stage_end_progress = STAGE_PROGRESS.get(stage_states[-1], 0)
                if state in stage_states:
                    st.markdown(f"**🔵{name}**")
                elif current_progress > stage_end_progress:
                    st.markdown(f"✅{name}")
                else:
                    st.markdown(f"⚪{name}")

        # ── Stage Readiness / Gate Blockers ─────────────────────────────────────
        readiness = st.session_state.stage_readiness or get_stage_readiness(
            st.session_state.session_id
        )
        st.session_state.stage_readiness = readiness
        stage_resolution = st.session_state.stage_resolution or get_stage_resolution(
            st.session_state.session_id
        )
        st.session_state.stage_resolution = stage_resolution
        state_stage_map = {
            "s1_running": 1,
            "s1_review": 1,
            "s2_running": 2,
            "s2_review": 2,
            "s3_running": 3,
            "s3_review": 3,
            "s4_running": 4,
            "s4_review": 4,
            "complete": 4,
        }
        current_stage_id = state_stage_map.get(state)
        if current_stage_id:
            current_readiness = readiness.get(f"stage_{current_stage_id}", {})
            advancement_decision = get_stage_advancement_decision(
                st.session_state.session_id, current_stage_id
            )
            blockers = current_readiness.get("blockers", []) or []
            can_continue = advancement_decision.get(
                "can_advance", current_readiness.get("can_continue", False)
            )
            gate_label = (
                "✅ 当前阶段可推进" if can_continue else f"🧭 阶段推进阻断器 ({len(blockers)})"
            )
            with st.expander(gate_label, expanded=bool(blockers)):
                st.caption(
                    f"阶段 {current_stage_id} · 输出版本 v{current_readiness.get('stage_output_version', 1)} · "
                    "StageAdvancementDecision 是推进判断的统一来源。"
                )
                if advancement_decision:
                    st.caption(
                        f"decision_reason=`{advancement_decision.get('decision_reason')}` · "
                        f"lifecycle=`{advancement_decision.get('stage_lifecycle')}` · "
                        f"hard={advancement_decision.get('hard_blockers_count', 0)} · "
                        f"executable={advancement_decision.get('executable_operations_count', 0)}"
                    )
                if current_readiness.get("block_reason"):
                    st.warning(current_readiness["block_reason"])
                if blockers:
                    for blocker in blockers[:8]:
                        st.markdown(
                            f"- `{blocker.get('blocker_id')}` "
                            f"[{blocker.get('severity')}/{blocker.get('blocker_type')}] "
                            f"{blocker.get('message')}"
                        )
                        if blocker.get("action_id"):
                            st.caption(f"action_id: {blocker.get('action_id')}")
                        st.caption(f"required_resolution: {blocker.get('required_resolution')}")

                    stage_ops = advancement_decision.get("required_operations") or (
                        stage_resolution.get("by_stage") or {}
                    ).get(f"stage_{current_stage_id}", [])
                    if stage_ops:
                        st.markdown("**可执行解除操作：**")
                        for op in stage_ops[:8]:
                            label = (
                                f"{op.get('required_resolution')} · "
                                f"{op.get('blocker_type')} · "
                                f"{'hard' if op.get('hard_blocker') else 'overridable'}"
                            )
                            with st.expander(label, expanded=False):
                                st.markdown(op.get("frontend_hint") or "")
                                if op.get("action_id"):
                                    st.code(op.get("action_id"), language="text")
                                if op.get("api_path"):
                                    st.caption(f"API: {op.get('api_method')} {op.get('api_path')}")
                                elif op.get("api_hint"):
                                    st.caption(op.get("api_hint"))
                                payload_hint = op.get("payload_hint") or {}
                                if payload_hint:
                                    st.json(payload_hint)
                                if (
                                    op.get("can_execute_via_api")
                                    and op.get("api_path")
                                    and op.get("required_resolution")
                                    in {"rerun_stage", "revise_stage", "back_stage"}
                                ):
                                    stage_op = {
                                        "rerun_stage": "rerun",
                                        "revise_stage": "revise",
                                        "back_stage": "rollback",
                                    }[op.get("required_resolution")]
                                    default_body = (
                                        payload_hint if isinstance(payload_hint, dict) else {}
                                    )
                                    if st.button(
                                        "执行该阶段操作",
                                        key=f"stage_op_{op.get('operation_id')}",
                                        use_container_width=True,
                                    ):
                                        result = prepare_stage_operation(
                                            st.session_state.session_id,
                                            int(op.get("stage_id")),
                                            stage_op,
                                            default_body,
                                        )
                                        if result:
                                            st.success(
                                                "阶段操作已记录；未运行 LLM/pytest/API/前端/Docker。"
                                            )
                                            st.session_state.stage_readiness = {}
                                            st.session_state.stage_resolution = {}
                                            refresh_actions()
                                            st.rerun()
                                if not op.get("action_id") and op.get("required_resolution") in {
                                    "resolve_action",
                                    "edit_stage_output",
                                    "approve_escalation",
                                }:
                                    if st.button(
                                        "同步缺失审核动作",
                                        key=f"sync_actions_{op.get('operation_id')}",
                                        use_container_width=True,
                                    ):
                                        result = prepare_stage_operation(
                                            st.session_state.session_id,
                                            int(op.get("stage_id")),
                                            "sync-review-actions",
                                            {"reason": "frontend_sync_missing_action_binding"},
                                        )
                                        if result:
                                            st.success(
                                                "已同步审核动作；请刷新后在人工动作队列处理。"
                                            )
                                            st.session_state.stage_readiness = {}
                                            st.session_state.stage_resolution = {}
                                            refresh_actions()
                                            st.rerun()
                    else:
                        st.caption(
                            "当前 blocker 暂无可绑定 API 的解除操作，请按 required_resolution 处理；resolved/superseded 历史 action 不会显示为可执行 API。"
                        )
                else:
                    st.success("当前阶段没有结构化 blocker。")

                operations = current_readiness.get("recommended_next_operations") or []
                if operations:
                    st.markdown("**下一步建议操作：**")
                    for op in operations:
                        st.caption(f"- {op}")

                metadata = current_readiness.get("stage_metadata") or {}
                if current_stage_id == 2 and metadata.get("stage_2_coverage_matrix"):
                    st.caption("Stage 2 high-risk coverage matrix 已生成，可在报告/API 中查看。")
                if current_stage_id == 3 and metadata.get("stage_3_coverage_warning", {}).get(
                    "coverage_warning"
                ):
                    missing = metadata["stage_3_coverage_warning"].get(
                        "missing_eval_coverage_node_ids", []
                    )
                    st.warning(
                        f"高风险节点缺少 EvalCase 覆盖，需补充 Stage3 structured_output 或回退重跑：{', '.join(missing)}"
                    )
                if current_stage_id == 4 and metadata.get("final_governance_summary"):
                    summary = metadata["final_governance_summary"]
                    st.caption(
                        "Final governance: "
                        f"critical_safety={len(summary.get('open_critical_safety_findings', []))}, "
                        f"pending_blockers={len(summary.get('pending_blocking_action_ids', []))}"
                    )

        st.divider()

        # ── Human Oversight 动作队列 ───────────────────────────────────────────
        refresh_actions()
        actions = st.session_state.pending_actions
        action_title = f"🚦 待处理人工动作 ({len(actions)})" if actions else "✅ 无待处理人工动作"
        st.subheader(action_title)

        if actions:
            st.caption("阻断型动作未处理前，后端会拒绝通过「确认」进入下一阶段。")
            for action in actions:
                risk = action.get("risk_level", "medium")
                action_type = action.get("action_type", "")
                title = action.get("title", "未命名动作")
                action_id = action.get("action_id", "")
                blocking = "阻断" if action.get("blocking", True) else "非阻断"
                version = action.get("stage_output_version", 1)
                with st.expander(
                    f"[阶段{action.get('stage_id')} v{version}] {risk}/{action_type}/{blocking} · {title}",
                    expanded=False,
                ):
                    st.code(action_id, language="text")
                    st.caption(f"阶段输出版本：v{version}")
                    st.markdown(f"**触发原因：** {action.get('trigger_reason') or '未提供'}")
                    st.markdown(f"**说明：** {action.get('description') or ''}")
                    payload_before = action.get("payload_before") or {}
                    if payload_before:
                        with st.expander("查看 AI 原始 payload", expanded=False):
                            st.json(payload_before)

                    note_key = f"action_note_{action_id}"
                    note = st.text_input(
                        "处理备注",
                        key=note_key,
                        placeholder="填写审批、核验或驳回理由...",
                    )

                    if action_type == "verify_evidence":
                        col_a, col_b = st.columns(2)
                        with col_a:
                            if st.button(
                                "✅ 已核验",
                                key=f"verify_action_{action_id}",
                                use_container_width=True,
                            ):
                                if resolve_action(
                                    st.session_state.session_id, action_id, "verify_evidence", note
                                ):
                                    refresh_flags()
                                    refresh_actions()
                                    st.rerun()
                        with col_b:
                            if st.button(
                                "❌ 忽略并留痕",
                                key=f"dismiss_action_{action_id}",
                                use_container_width=True,
                            ):
                                if resolve_action(
                                    st.session_state.session_id, action_id, "dismissed", note
                                ):
                                    refresh_flags()
                                    refresh_actions()
                                    st.rerun()

                    elif action_type == "approve":
                        col_a, col_b = st.columns(2)
                        with col_a:
                            if st.button(
                                "✅ 批准继续",
                                key=f"approve_action_{action_id}",
                                use_container_width=True,
                            ):
                                if resolve_action(
                                    st.session_state.session_id, action_id, "approve", note
                                ):
                                    refresh_flags()
                                    refresh_actions()
                                    st.rerun()
                        with col_b:
                            if st.button(
                                "❌ 驳回并要求修改",
                                key=f"reject_action_{action_id}",
                                use_container_width=True,
                            ):
                                if resolve_action(
                                    st.session_state.session_id, action_id, "reject", note
                                ):
                                    refresh_flags()
                                    refresh_actions()
                                    st.warning(
                                        "该关键动作已驳回。请使用聊天区输入「修改」或「回退」后再继续。"
                                    )
                                    st.rerun()

                    elif action_type == "escalate":
                        st.warning(
                            "该动作属于 critical/escalate，必须明确批准或回退修改，不能忽略关闭。"
                        )
                        if st.button(
                            "🧑‍⚖️ 升级风险已明确批准",
                            key=f"escalate_approve_{action_id}",
                            use_container_width=True,
                        ):
                            if resolve_action(
                                st.session_state.session_id, action_id, "approve", note
                            ):
                                refresh_flags()
                                refresh_actions()
                                st.rerun()

                    elif action_type == "edit":
                        edit_text = st.text_area(
                            "人工修改后的摘要 / 处理方案（必填）",
                            key=f"action_edit_{action_id}",
                            height=100,
                        )
                        source_type = action.get("source_type")
                        structured_required = source_type in STRUCTURED_EDIT_SOURCE_TYPES
                        if structured_required:
                            st.warning(
                                "该 edit 来源要求完整 structured_output；仅填写摘要/备注不能解除阶段推进 blocker。"
                            )
                        else:
                            st.caption(
                                "普通 edit 只会作为人工处理记录；若要改变阶段结构化输出，请提交 structured_output。"
                            )
                        structured_text = st.text_area(
                            "结构化 JSON（必填）"
                            if structured_required
                            else "结构化 JSON（可选；填写后会校验并反写 stage_X_output）",
                            key=f"action_structured_{action_id}",
                            height=120,
                            placeholder='例如：{"failure_modes":[...],"direct_conclusion":"..."}',
                        )
                        col_a, col_b = st.columns(2)
                        with col_a:
                            if st.button(
                                "✏️ 编辑后通过",
                                key=f"edit_action_{action_id}",
                                use_container_width=True,
                            ):
                                if structured_required and not structured_text.strip():
                                    st.error(
                                        "parser/policy/evidence/eval_coverage 类 edit 必须提交完整结构化 JSON。"
                                    )
                                elif not edit_text.strip() and not structured_text.strip():
                                    st.error("edit 动作必须填写人工修改内容或结构化 JSON。")
                                else:
                                    payload_after = {
                                        "edited_text": edit_text.strip(),
                                        "reviewer_note": note,
                                    }
                                    if structured_text.strip():
                                        try:
                                            payload_after["structured_output"] = json.loads(
                                                structured_text
                                            )
                                        except json.JSONDecodeError as exc:
                                            st.error(f"结构化 JSON 解析失败：{exc}")
                                            st.stop()
                                    if resolve_action(
                                        st.session_state.session_id,
                                        action_id,
                                        "edit",
                                        note,
                                        payload_after=payload_after,
                                    ):
                                        refresh_flags()
                                        refresh_actions()
                                        st.rerun()
                        with col_b:
                            if st.button(
                                "❌ 驳回，需重跑",
                                key=f"edit_reject_{action_id}",
                                use_container_width=True,
                            ):
                                if resolve_action(
                                    st.session_state.session_id, action_id, "reject", note
                                ):
                                    refresh_flags()
                                    refresh_actions()
                                    st.warning(
                                        "该编辑动作已驳回。请使用「修改」或「回退」重新生成。"
                                    )
                                    st.rerun()

        st.divider()

        # ── 【需核验】面板 ─────────────────────────────────────────────────────
        pending = st.session_state.pending_flags
        flag_title = f"⚠️ 待核验 ({len(pending)})" if pending else "✅ 无待核验项"
        st.subheader(flag_title)

        if pending:
            for flag in pending:
                short_content = (
                    flag["content"][:25] + "…" if len(flag["content"]) > 25 else flag["content"]
                )
                with st.expander(f"[阶段{flag['stage']}] {short_content}", expanded=False):
                    st.markdown(f"**内容：** {flag['content']}")
                    if flag.get("context"):
                        st.caption(f"上下文：{flag['context'][:120]}")

                    note_key = f"flag_note_{flag['item_id']}"
                    note = st.text_input(
                        "核验备注（可选）",
                        key=note_key,
                        placeholder="填写核验结论...",
                    )

                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        if st.button(
                            "✅ 已核验",
                            key=f"verify_{flag['item_id']}",
                            use_container_width=True,
                        ):
                            if resolve_flag(
                                st.session_state.session_id,
                                flag["item_id"],
                                "verified",
                                note,
                            ):
                                st.session_state.pending_flags = [
                                    f
                                    for f in st.session_state.pending_flags
                                    if f["item_id"] != flag["item_id"]
                                ]
                                st.rerun()
                    with btn_col2:
                        if st.button(
                            "❌ 忽略",
                            key=f"dismiss_{flag['item_id']}",
                            use_container_width=True,
                        ):
                            if resolve_flag(
                                st.session_state.session_id,
                                flag["item_id"],
                                "dismissed",
                                note,
                            ):
                                st.session_state.pending_flags = [
                                    f
                                    for f in st.session_state.pending_flags
                                    if f["item_id"] != flag["item_id"]
                                ]
                                st.rerun()

        st.divider()

        # ── Evidence / Safety 面板 ──────────────────────────────────────────────
        with st.expander("📚 证据来源 Evidence", expanded=False):
            evidence_items = list_evidence(st.session_state.session_id)
            if evidence_items:
                verified_total = sum(1 for e in evidence_items if e.get("verified"))
                st.caption(
                    f"{len(evidence_items)} total · "
                    f"{verified_total} verified · "
                    f"{len(evidence_items) - verified_total} unverified"
                )
                for ev in evidence_items:
                    verified = ev.get("verified", False)
                    score = ev.get("credibility_score", 0.0)
                    status_icon = "✅" if verified else "⚪"
                    status_text = "已核验" if verified else "未核验"
                    st.markdown(
                        f"{status_icon} **`{ev.get('evidence_id')}`** · "
                        f"{ev.get('source_type')} · "
                        f"score={score:.2f} · {status_text}"
                    )
                    st.caption(ev.get("title", ""))
                    if ev.get("url"):
                        st.caption(ev.get("url"))
                    if ev.get("summary"):
                        st.caption(ev["summary"][:200])
                    claims = ev.get("claims") or []
                    if claims:
                        with st.expander(f"Claims ({len(claims)})", expanded=False):
                            for claim in claims:
                                st.markdown(f"- {claim}")
                    if ev.get("used_by_failure_mode_ids"):
                        st.caption(
                            "Linked failure modes: "
                            + ", ".join(ev.get("used_by_failure_mode_ids", []))
                        )
                    if verified and ev.get("verification_note"):
                        st.caption(f"Verification note: {ev['verification_note']}")
                    if not verified and score < 0.4:
                        st.warning(
                            "Low credibility — unverified weak sources may weaken downstream analysis."
                        )
                    note_key = f"evidence_note_{ev.get('evidence_id')}"
                    ev_note = st.text_input("核验备注", key=note_key)
                    if not verified:
                        if st.button(
                            "✅ 核验证据",
                            key=f"verify_ev_{ev.get('evidence_id')}",
                            use_container_width=True,
                        ):
                            if verify_evidence(
                                st.session_state.session_id, ev.get("evidence_id"), ev_note
                            ):
                                refresh_actions()
                                st.success("证据已核验；若有关联的低可信证据动作，会自动关闭。")
                                st.rerun()
                    st.divider()
            else:
                st.caption("暂无证据来源。阶段一搜索完成后会自动生成。")

        with st.expander("🛡️ Safety Findings", expanded=False):
            findings = list_safety_findings(st.session_state.session_id, status="open")
            if findings:
                high_crit_open = sum(
                    1
                    for f in findings
                    if f.get("status") == "open" and f.get("severity") in {"high", "critical"}
                )
                st.caption(f"{len(findings)} open · {high_crit_open} high/critical unresolved")
                for finding in findings:
                    severity = finding.get("severity", "low")
                    is_high_crit = severity in {"high", "critical"}
                    severity_icon = {
                        "critical": "🔴",
                        "high": "🟠",
                        "medium": "🟡",
                        "low": "⚪",
                    }.get(severity, "⚪")
                    st.markdown(
                        f"{severity_icon} **`{finding.get('finding_id')}`** · stage={finding.get('stage_id')} · "
                        f"{severity}/{finding.get('risk_type')}"
                    )
                    st.caption(finding.get("description", ""))
                    st.caption("Recommended: " + finding.get("recommended_action", ""))
                    if is_high_crit:
                        st.warning(
                            "High/critical unresolved safety finding — "
                            "may block stage advancement or require human review."
                        )
                    finding_note = st.text_input(
                        "处理备注", key=f"safety_note_{finding.get('finding_id')}"
                    )
                    requires_review = finding.get("requires_human_review")
                    if requires_review and is_high_crit:
                        st.caption('该高风险安全发现已派生阻断动作，请到"待处理人工动作"面板处理。')
                        if st.button(
                            "✅ 标记已处理",
                            key=f"resolve_safety_{finding.get('finding_id')}",
                            use_container_width=True,
                        ):
                            if resolve_safety_finding(
                                st.session_state.session_id,
                                finding.get("finding_id"),
                                "resolved",
                                finding_note,
                            ):
                                refresh_actions()
                                st.rerun()
                    else:
                        col_resolve, col_dismiss = st.columns(2)
                        with col_resolve:
                            if st.button(
                                "✅ 已处理",
                                key=f"resolve_safety_{finding.get('finding_id')}",
                                use_container_width=True,
                            ):
                                if resolve_safety_finding(
                                    st.session_state.session_id,
                                    finding.get("finding_id"),
                                    "resolved",
                                    finding_note,
                                ):
                                    refresh_actions()
                                    st.rerun()
                        with col_dismiss:
                            if st.button(
                                "📝 忽略留痕",
                                key=f"dismiss_safety_{finding.get('finding_id')}",
                                use_container_width=True,
                            ):
                                if resolve_safety_finding(
                                    st.session_state.session_id,
                                    finding.get("finding_id"),
                                    "dismissed",
                                    finding_note,
                                ):
                                    refresh_actions()
                                    st.rerun()
                    st.divider()
            else:
                st.caption("暂无未关闭安全发现。")

        with st.expander("🧩 Execution / Interrupt Debug", expanded=False):
            records = st.session_state.interrupt_records or list_interrupt_records(
                st.session_state.session_id
            )
            health = st.session_state.health or get_health()
            st.caption(
                "默认 single_step 保持稳定；"
                "启用 WORKFLOW_EXECUTION_MODE=langgraph_interrupt 后使用 checkpoint-backed interrupt/resume；"
                "action/interrupt 同步由执行协调层处理。"
            )
            if health:
                st.caption(
                    f"Mode: `{health.get('workflow_execution_mode', 'unknown')}` · "
                    f"Adapter: `{health.get('interrupt_adapter_status', 'unknown')}`"
                )
            if records:
                summary = {
                    "total": len(records),
                    "pending": len([r for r in records if r.get("status") == "pending"]),
                    "resumed": len([r for r in records if r.get("status") == "resumed"]),
                    "cancelled": len([r for r in records if r.get("status") == "cancelled"]),
                    "resume_consumed": len(
                        [
                            r
                            for r in records
                            if r.get("status") == "resumed" and r.get("resume_consumed_at")
                        ]
                    ),
                    "resume_pending": len(
                        [
                            r
                            for r in records
                            if r.get("status") == "resumed" and not r.get("resume_consumed_at")
                        ]
                    ),
                }
                st.json(summary)
                for record in records:
                    label = (
                        f"{record.get('status')} · {record.get('interrupt_id')} "
                        f"↔ {record.get('action_id')} · stage={record.get('stage_id')}"
                    )
                    with st.expander(label, expanded=False):
                        if record.get("status") == "resumed" and not record.get(
                            "resume_consumed_at"
                        ):
                            st.warning(
                                "该 interrupt 已标记 resumed，但 Command(resume=...) 尚未消费。"
                            )
                        elif record.get("status") == "cancelled":
                            st.info("该 interrupt 已取消，不会恢复执行。")
                        elif record.get("resume_consumed_at"):
                            st.success(f"Resume consumed at: {record.get('resume_consumed_at')}")
                        st.json(record)
            else:
                st.caption(
                    "暂无 interrupt records。阻断型 PendingHumanAction 出现后会自动创建映射记录。"
                )

        with st.expander("🛡️ Red Team Coverage", expanded=False):
            redteam_cases = list_redteam_cases(st.session_state.session_id)
            redteam_coverage = get_redteam_coverage(st.session_state.session_id)
            render_redteam_panel(cases=redteam_cases, coverage=redteam_coverage)

            col_generate, col_dataset = st.columns(2)
            with col_generate:
                if st.button("🧪 Generate RedTeamCase drafts", use_container_width=True):
                    created = generate_redteam_cases(st.session_state.session_id)
                    st.success(f"Generated {len(created)} RedTeamCase draft(s).")
                    refresh_actions()
                    st.rerun()
            with col_dataset:
                if st.button("📦 Create redteam dataset", use_container_width=True):
                    dataset = create_redteam_dataset(st.session_state.session_id)
                    if dataset:
                        st.success(f"Dataset created: {dataset.get('dataset_id')}")
                        refresh_actions()
                        st.rerun()

            for case in redteam_cases:
                case_id = case.get("redteam_case_id")
                if not case_id:
                    continue
                cols = st.columns(3)
                with cols[0]:
                    if case.get("status") == "draft" and st.button(
                        f"✅ Approve {case_id}",
                        key=f"approve_redteam_{case_id}",
                        use_container_width=True,
                    ):
                        approve_redteam_case(
                            st.session_state.session_id, case_id, "Approved in Review Workbench"
                        )
                        refresh_actions()
                        st.rerun()
                with cols[1]:
                    if case.get("status") == "draft" and st.button(
                        f"📝 Reject {case_id}",
                        key=f"reject_redteam_{case_id}",
                        use_container_width=True,
                    ):
                        reject_redteam_case(
                            st.session_state.session_id, case_id, "Rejected in Review Workbench"
                        )
                        refresh_actions()
                        st.rerun()
                with cols[2]:
                    if case.get("status") == "approved" and st.button(
                        f"🔗 Sync {case_id}",
                        key=f"sync_redteam_{case_id}",
                        use_container_width=True,
                    ):
                        eval_case = sync_redteam_case_to_eval(st.session_state.session_id, case_id)
                        if eval_case:
                            st.success(f"Synced to EvalCase: {eval_case.get('eval_id')}")
                        refresh_actions()
                        st.rerun()

        with st.expander("🧪 Eval Cases / Datasets / Experiments", expanded=False):
            eval_cases = list_eval_cases(st.session_state.session_id)
            eval_runs = list_eval_runs(st.session_state.session_id)
            eval_datasets = list_eval_datasets(st.session_state.session_id)
            eval_experiments = list_eval_experiments(st.session_state.session_id)

            st.caption(
                "EvalDataset / EvalExperiment / Regression Gate / "
                "Trace Backfill Gate are available at source level; runtime validation remains deferred."
            )
            metric_cols = st.columns(4)
            metric_cols[0].metric("EvalCases", len(eval_cases))
            metric_cols[1].metric("Datasets", len(eval_datasets))
            metric_cols[2].metric("Experiments", len(eval_experiments))
            metric_cols[3].metric("EvalRuns", len(eval_runs))

            with st.expander(
                "Dataset / Experiment foundation", expanded=bool(eval_datasets or eval_experiments)
            ):
                dataset_name = st.text_input(
                    "Dataset name",
                    value="Stage 3 generated dataset",
                    key="eval_dataset_name",
                )
                if st.button("📦 Create dataset from Stage 3", use_container_width=True):
                    dataset = create_eval_dataset_from_stage3(
                        st.session_state.session_id,
                        dataset_name,
                        "Created from current Stage 3 EvalCases.",
                    )
                    if dataset:
                        st.success(f"Dataset created: {dataset.get('dataset_id')}")
                        st.rerun()

                if eval_datasets:
                    dataset_options = {
                        f"{dataset.get('dataset_id')} · {dataset.get('name')}": dataset
                        for dataset in eval_datasets
                    }
                    selected_dataset_label = st.selectbox(
                        "Select dataset",
                        options=list(dataset_options.keys()),
                        key="selected_eval_dataset",
                    )
                    selected_dataset = dataset_options[selected_dataset_label]
                    st.caption(
                        f"cases={len(selected_dataset.get('case_ids') or [])} · "
                        f"source={selected_dataset.get('source')} · "
                        f"baseline={selected_dataset.get('baseline_experiment_id') or '-'}"
                    )
                    experiment_name = st.text_input(
                        "Experiment name",
                        value=f"Experiment for {selected_dataset.get('name')}",
                        key="eval_experiment_name",
                    )
                    experiment_run_mode = st.selectbox(
                        "Experiment run mode",
                        ["manual", "dry_run", "llm_node"],
                        index=1,
                        key="eval_experiment_run_mode",
                    )
                    baseline_options = {"[none]": None}
                    baseline_options.update(
                        {
                            f"{exp.get('experiment_id')} · {exp.get('name')}": exp.get(
                                "experiment_id"
                            )
                            for exp in eval_experiments
                            if exp.get("dataset_id") == selected_dataset.get("dataset_id")
                        }
                    )
                    selected_baseline_label = st.selectbox(
                        "Baseline experiment",
                        options=list(baseline_options.keys()),
                        key="selected_eval_baseline",
                    )
                    if st.button("🧪 Create experiment", use_container_width=True):
                        experiment = create_eval_experiment(
                            st.session_state.session_id,
                            selected_dataset.get("dataset_id"),
                            experiment_name,
                            experiment_run_mode,
                            baseline_options[selected_baseline_label],
                        )
                        if experiment:
                            st.success(f"Experiment created: {experiment.get('experiment_id')}")
                            st.rerun()

                if eval_experiments:
                    st.markdown("**Experiments**")
                    for experiment in eval_experiments:
                        metrics = experiment.get("aggregate_metrics") or {}
                        comparison = experiment.get("comparison_summary") or {}
                        st.markdown(
                            f"- `{experiment.get('experiment_id')}` · {experiment.get('name')} · "
                            f"{experiment.get('status')} · mode={experiment.get('run_mode')} · "
                            f"pass_rate={metrics.get('pass_rate', 0):.2f}"
                        )
                        if experiment.get("status") in {"created", "failed"}:
                            if st.button(
                                f"▶️ Run {experiment.get('experiment_id')}",
                                key=f"run_experiment_{experiment.get('experiment_id')}",
                                use_container_width=True,
                            ):
                                result = run_eval_experiment(
                                    st.session_state.session_id,
                                    experiment.get("experiment_id"),
                                    dry_run_only=True,
                                )
                                if result:
                                    refresh_actions()
                                    st.success("Experiment run completed or recorded.")
                                    st.rerun()
                        if comparison:
                            if comparison.get("regression_detected"):
                                st.warning(
                                    f"Comparison detected regression: {comparison.get('regression_reasons')}"
                                )
                            else:
                                st.success("Comparison summary: no regression detected.")

            run_mode = st.selectbox(
                "Legacy EvalCase run mode", ["manual", "dry_run", "llm_node"], key="eval_run_mode"
            )
            if eval_cases:
                col_run_all, col_refresh_runs = st.columns(2)
                with col_run_all:
                    if st.button("▶️ Run all EvalCases", use_container_width=True):
                        result = run_eval_cases(st.session_state.session_id, None, run_mode)
                        if result:
                            refresh_actions()
                            st.success(f"Created {len(result.get('created_runs', []))} EvalRun(s).")
                            st.rerun()
                with col_refresh_runs:
                    st.caption(f"EvalRuns: {len(eval_runs)}")

                for case in eval_cases:
                    st.markdown(
                        f"**`{case.get('eval_id')}`** · node={case.get('target_node_id')} · "
                        f"{case.get('scenario_type')} · passed={case.get('passed')}"
                    )
                    st.caption("Input: " + (case.get("input_payload") or "")[:300])
                    st.caption("Expected: " + (case.get("expected_behavior") or "")[:300])
                    if st.button(
                        "▶️ Run this case",
                        key=f"run_eval_{case.get('eval_id')}",
                        use_container_width=True,
                    ):
                        result = run_single_eval_case(
                            st.session_state.session_id, case.get("eval_id"), run_mode
                        )
                        if result:
                            refresh_actions()
                            st.rerun()
                    case_runs = [
                        run for run in eval_runs if run.get("eval_id") == case.get("eval_id")
                    ]
                    if case_runs:
                        latest_run = case_runs[-1]
                        st.caption(
                            "Latest run: "
                            f"{latest_run.get('run_id')} · status={latest_run.get('status')} · "
                            f"judge={latest_run.get('judge_result')}"
                        )
                    score_key = f"eval_score_{case.get('eval_id')}"
                    comment_key = f"eval_comment_{case.get('eval_id')}"
                    pass_key = f"eval_passed_{case.get('eval_id')}"
                    actual_key = f"eval_actual_{case.get('eval_id')}"
                    actual_value = st.text_area(
                        "Actual output",
                        value=case.get("actual_output") or "",
                        key=actual_key,
                        height=90,
                    )
                    score_value = st.slider(
                        "人工评分（1-5）", 1, 5, int(case.get("human_score") or 3), key=score_key
                    )
                    passed_value = st.selectbox(
                        "人工结论", ["未定", "通过", "不通过"], key=pass_key
                    )
                    comment_value = st.text_input(
                        "评分备注", value=case.get("human_comment") or "", key=comment_key
                    )
                    passed_bool = None if passed_value == "未定" else passed_value == "通过"
                    if st.button(
                        "💾 保存评分",
                        key=f"score_eval_{case.get('eval_id')}",
                        use_container_width=True,
                    ):
                        if score_eval_case(
                            st.session_state.session_id,
                            case.get("eval_id"),
                            score_value,
                            comment_value,
                            passed_bool,
                            actual_value,
                        ):
                            refresh_actions()
                            st.rerun()
                    st.divider()
            else:
                st.caption("暂无 EvalCase。阶段三压测完成后会自动生成。")

        st.divider()

        # ── 审计历史 ───────────────────────────────────────────────────────────
        with st.expander("🧾 审计历史", expanded=False):
            events = list_audit_events(st.session_state.session_id)
            if events:
                st.caption(f"{len(events)} audit events recorded (showing last 30)")
                for event in events[-30:]:
                    event_type = event.get("event_type", "?")
                    actor = event.get("actor", "system")
                    created_at = event.get("created_at", "")
                    target_type = event.get("target_type", "")
                    target_id = event.get("target_id", "")
                    metadata = event.get("metadata") or {}

                    label = (
                        f"{created_at[:19] if created_at else '?'}  ·  "
                        f"{actor}  ·  "
                        f"{event_type}  ·  "
                        f"{target_type}/{target_id}"
                    )
                    with st.expander(label, expanded=False):
                        st.caption(f"Event type: **{event_type}**")
                        st.caption(f"Actor: {actor}  ·  Timestamp: {created_at}")
                        st.caption(f"Target: {target_type}/{target_id}")
                        if metadata:
                            with st.expander("Metadata", expanded=False):
                                st.json(metadata)
            else:
                st.caption("暂无审计事件。")

        st.divider()

        # ── 报告面板 ───────────────────────────────────────────────────────────
        st.subheader("Report Workbench")

        # --- Export (live snapshot) ---
        with st.expander("Export Live Snapshot", expanded=False):
            col_json, col_md = st.columns(2)
            with col_json:
                if st.button("Generate JSON", use_container_width=True, key="export_json_btn"):
                    with st.spinner("Generating..."):
                        report = export_report(st.session_state.session_id, format="json")
                    if report:
                        report_json = json.dumps(report, ensure_ascii=False, indent=2)
                        sid_short = st.session_state.session_id[:8]
                        st.download_button(
                            label="Download JSON",
                            data=report_json,
                            file_name=f"workflow_report_{sid_short}.json",
                            mime="application/json",
                            use_container_width=True,
                        )
                    else:
                        st.error("Failed to generate JSON report.")
            with col_md:
                if st.button("Generate Markdown", use_container_width=True, key="export_md_btn"):
                    with st.spinner("Generating..."):
                        report = export_report(st.session_state.session_id, format="markdown")
                    if report and report.get("content"):
                        sid_short = st.session_state.session_id[:8]
                        st.download_button(
                            label="Download Markdown",
                            data=report["content"],
                            file_name=f"workflow_report_{sid_short}.md",
                            mime="text/markdown",
                            use_container_width=True,
                        )
                    else:
                        st.error("Failed to generate Markdown report.")

        # --- Versioned artifacts ---
        st.divider()
        if st.button("Create Report Snapshot", use_container_width=True, key="create_artifact_btn"):
            artifact = create_report_artifact(st.session_state.session_id)
            if artifact:
                st.success(f"Snapshot created: {artifact.get('report_id')}")
            else:
                st.error("Failed to create report snapshot.")

        artifacts = list_report_artifacts(st.session_state.session_id)
        if artifacts:
            report_options = {
                f"{a.get('report_id', '?')[:12]}... (v{a.get('version', '?')}, {a.get('generated_at', '?')[:19]})": a
                for a in reversed(artifacts[-20:])
            }
            selected_label = st.selectbox(
                "Select a report artifact to view",
                options=["[none]"] + list(report_options.keys()),
                key="selected_report_label",
            )
            if selected_label and selected_label != "[none]":
                selected_artifact = report_options[selected_label]
                report_id = selected_artifact.get("report_id", "")
                # Fetch full artifact from API (includes content_json/content_markdown)
                full_report = get_report_artifact(st.session_state.session_id, report_id)
                if full_report:
                    render_report_panel(full_report)
                else:
                    st.error(f"Failed to load report {report_id}. The backend may be unavailable.")
            else:
                st.caption("No report selected. Pick one from the dropdown above to view.")
        else:
            st.info("No report artifacts yet. Create a snapshot or export a live report above.")


# ─────────────────────────────────────────────────────────────────────────────
# 主区域
# ─────────────────────────────────────────────────────────────────────────────

if not st.session_state.session_id:
    # ── 欢迎页 ────────────────────────────────────────────────────────────────
    st.markdown("""
    # 👋 欢迎使用 AI Workflow Review Workbench

    面向 AI 项目立项阶段的 **Pre-mortem、Human Oversight、Evidence、Safety、Eval 与 Audit-ready Report** 工作台。

    ---

    ## 🚀 快速开始

    点击左侧 **「➕ 新建会话」** 即可开始。

    ---

    ## 📋 四个确定性分析阶段

    | 阶段 | 内容 | 重点 |
    |------|------|------|
    | 阶段一 | Failure Mode Pre-mortem | 结合证据识别失败模式，并保留 `evidence_ids` |
    | 阶段二 | Human Oversight Workflow | 针对高风险节点设计人工审核策略 |
    | 阶段三 | Stress Test / Eval Cases | 生成压测用例并沉淀覆盖率指标 |
    | 阶段四 | Trigger Methods | 输出触发方式，并检查高风险触发是否需要人工复核 |

    ---

    ## 💡 核心特性

    - **Human Oversight Action Queue**：阻断型人工动作会阻止阶段自动推进
    - **Evidence-grounded Risk Analysis**：搜索资料和用户补充资料都会进入 EvidenceSource
    - **Safety Findings**：轻量检测 prompt injection、unsupported claim、policy gap 等风险
    - **Eval Coverage Summary**：统计失败模式覆盖率、高风险节点覆盖率等指标
    - **Audit-ready Reports**：导出包含证据、安全、审核、压测和开放风险的报告
    """)

else:
    # ── 对话区 ────────────────────────────────────────────────────────────────

    # 渲染对话历史
    for msg in st.session_state.messages:
        role = msg["role"]
        content = msg["content"]
        metadata = msg.get("metadata", {})
        reasoning = metadata.get("reasoning", "")

        if role == "assistant":
            with st.chat_message("assistant", avatar="🤖"):
                if reasoning:
                    with st.expander("🧠 查看推理过程（DeepSeek V4 thinking）", expanded=False):
                        st.markdown(
                            f"<div style='color:#888;font-size:0.85em;'>{reasoning}</div>",
                            unsafe_allow_html=True,
                        )
                st.markdown(content)

        elif role == "user":
            with st.chat_message("user", avatar="👤"):
                st.markdown(content)

    # ── 资料上传区 ────────────────────────────────────────────────────────────
    with st.expander("📎 补充参考资料（可选）", expanded=False):
        st.caption(
            "粘贴文档、研究报告、使用经验等，AI 将在下一轮分析中参考这些内容。"
            "资料添加后立即生效，无需重新发送消息。"
        )

        material_text = st.text_area(
            "粘贴文本内容",
            height=100,
            placeholder="粘贴任意文本...",
            key="material_text_input",
        )
        uploaded_file = st.file_uploader(
            "或上传文件（.txt / .md）",
            type=["txt", "md"],
            key="file_uploader",
        )

        if st.button("✅ 添加到本次分析", use_container_width=True):
            materials: list[str] = []
            if material_text.strip():
                materials.append(material_text.strip())
            if uploaded_file is not None:
                file_content = uploaded_file.read().decode("utf-8", errors="ignore")
                materials.append(f"[文件：{uploaded_file.name}]\n{file_content}")

            if materials:
                with st.spinner("上传中..."):
                    ok = add_materials_to_session(st.session_state.session_id, materials)
                if ok:
                    st.success(f"✅ 已添加 {len(materials)} 份资料。")
                else:
                    st.error("上传失败，请重试。")
            else:
                st.warning("请先输入或上传资料内容。")

    # ── 快捷操作按钮（仅在 review 状态显示）────────────────────────────────
    state = st.session_state.current_state
    review_states = {"s1_review", "s2_review", "s3_review", "s4_review"}

    if state in review_states:
        st.markdown("---")
        st.markdown("**⚡ 快捷操作**")

        # 基础三个操作
        quick_cols = st.columns(4)
        quick_actions = [
            (quick_cols[0], "✅ 确认，进入下一阶段", "确认"),
            (quick_cols[1], "⬅️ 回退上一阶段", "回退"),
        ]

        # 阶段三额外提供「回退工作流」
        if state == "s3_review":
            quick_actions.append((quick_cols[2], "🔁 回退到工作流设计", "回退工作流"))

        for col, btn_label, action_text in quick_actions:
            with col:
                if st.button(btn_label, use_container_width=True):
                    handle_send(action_text)
                    st.rerun()

    # ── 输入框 ────────────────────────────────────────────────────────────────
    placeholder = CHAT_PLACEHOLDER.get(state, "输入消息...")
    disabled = state == "complete"

    if user_input := st.chat_input(placeholder, disabled=disabled):
        handle_send(user_input)
        st.rerun()
