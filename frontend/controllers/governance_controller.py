# frontend/controllers/governance_controller.py
from __future__ import annotations

import json

import streamlit as st
from models.api_client import (
    calibrate_eval_run,
    request_release_approval,
    resolve_action,
    resolve_flag,
    resolve_safety_finding,
    review_risk_treatment,
    set_target_deployment,
    upsert_risk_treatment,
    verify_evidence,
)
from models.feedback import ApiError, show_api_error
from models.session_state import refresh_actions, refresh_flags


def handle_verify_action(action_id: str, note: str) -> None:
    try:
        resolve_action(
            st.session_state.session_id,
            action_id,
            "verify_evidence",
            note,
        )
    except ApiError as exc:
        show_api_error(exc)
        return
    refresh_flags()
    refresh_actions()
    st.rerun()


def handle_dismiss_action(action_id: str, note: str) -> None:
    try:
        resolve_action(st.session_state.session_id, action_id, "dismissed", note)
    except ApiError as exc:
        show_api_error(exc)
        return
    refresh_flags()
    refresh_actions()
    st.warning(
        "已忽略并留痕，但高风险证据门控可能仍未解除。请查看左侧「阶段推进阻断器」确认是否仍被阻断。"
    )
    st.rerun()


def handle_approve_action(action_id: str, note: str) -> None:
    try:
        resolve_action(st.session_state.session_id, action_id, "approve", note)
    except ApiError as exc:
        show_api_error(exc)
        return
    refresh_flags()
    refresh_actions()
    st.rerun()


def handle_reject_action(action_id: str, note: str) -> None:
    try:
        resolve_action(st.session_state.session_id, action_id, "reject", note)
    except ApiError as exc:
        show_api_error(exc)
        return
    refresh_flags()
    refresh_actions()
    st.warning("该关键动作已驳回。请使用聊天区输入「修改」或「回退」后再继续。")
    st.rerun()


def handle_escalate_action(action_id: str, note: str) -> None:
    try:
        resolve_action(st.session_state.session_id, action_id, "approve", note)
    except ApiError as exc:
        show_api_error(exc)
        return
    refresh_flags()
    refresh_actions()
    st.rerun()


def handle_edit_action(
    action_id: str,
    note: str,
    edit_text: str,
    structured_text: str,
    structured_required: bool,
) -> None:
    if structured_required and not structured_text.strip():
        st.error("parser/policy/evidence/eval_coverage 类 edit 必须提交完整结构化 JSON。")
        return
    if not edit_text.strip() and not structured_text.strip():
        st.error("edit 动作必须填写人工修改内容或结构化 JSON。")
        return
    payload_after = {
        "edited_text": edit_text.strip(),
        "reviewer_note": note,
    }
    if structured_text.strip():
        try:
            payload_after["structured_output"] = json.loads(structured_text)
        except json.JSONDecodeError as exc:
            st.error(f"结构化 JSON 解析失败：{exc}")
            st.stop()
    try:
        resolve_action(
            st.session_state.session_id,
            action_id,
            "edit",
            note,
            payload_after=payload_after,
        )
    except ApiError as exc:
        show_api_error(exc)
        return
    refresh_flags()
    refresh_actions()
    st.rerun()


def handle_edit_reject_action(action_id: str, note: str) -> None:
    try:
        resolve_action(st.session_state.session_id, action_id, "reject", note)
    except ApiError as exc:
        show_api_error(exc)
        return
    refresh_flags()
    refresh_actions()
    st.warning("该编辑动作已驳回。请使用「修改」或「回退」重新生成。")
    st.rerun()


def handle_verify_flag(flag_id: str, note: str) -> None:
    try:
        resolve_flag(
            st.session_state.session_id,
            flag_id,
            "verified",
            note,
        )
    except ApiError as exc:
        show_api_error(exc)
        return
    st.session_state.pending_flags = [
        f for f in st.session_state.pending_flags if f["item_id"] != flag_id
    ]
    st.rerun()


def handle_dismiss_flag(flag_id: str, note: str) -> None:
    try:
        resolve_flag(
            st.session_state.session_id,
            flag_id,
            "dismissed",
            note,
        )
    except ApiError as exc:
        show_api_error(exc)
        return
    st.session_state.pending_flags = [
        f for f in st.session_state.pending_flags if f["item_id"] != flag_id
    ]
    st.rerun()


def handle_verify_evidence_item(evidence_id: str, note: str) -> None:
    try:
        verify_evidence(st.session_state.session_id, evidence_id, note)
    except ApiError as exc:
        show_api_error(exc)
        return
    refresh_actions()
    st.success("证据已核验；若有关联的低可信证据动作，会自动关闭。")
    st.rerun()


def handle_resolve_safety_item(finding_id: str, note: str) -> None:
    try:
        resolve_safety_finding(
            st.session_state.session_id,
            finding_id,
            "resolved",
            note,
        )
    except ApiError as exc:
        show_api_error(exc)
        return
    refresh_actions()
    st.rerun()


def handle_dismiss_safety_item(finding_id: str, note: str) -> None:
    try:
        resolve_safety_finding(
            st.session_state.session_id,
            finding_id,
            "dismissed",
            note,
        )
    except ApiError as exc:
        show_api_error(exc)
        return
    refresh_actions()
    st.rerun()


def handle_upsert_treatment(
    source_type: str,
    source_id: str,
    owner: str,
    mitigation_plan: str,
    status: str,
    note: str,
) -> None:
    if not owner.strip() or not mitigation_plan.strip():
        st.error("责任人与缓解措施均为必填。")
        return
    try:
        upsert_risk_treatment(
            st.session_state.session_id,
            source_type=source_type,
            source_id=source_id,
            owner=owner.strip(),
            mitigation_plan=mitigation_plan.strip(),
            status=status,
            note=note,
        )
    except ApiError as exc:
        show_api_error(exc)
        return
    st.success("风险处置已保存；修改处置内容会清空旧复核记录。")
    st.rerun()


def handle_review_treatment(treatment_id: str, decision: str, note: str) -> None:
    try:
        review_risk_treatment(
            st.session_state.session_id,
            treatment_id=treatment_id,
            decision=decision,
            note=note,
        )
    except ApiError as exc:
        show_api_error(exc)
        return
    st.success("风险处置复核结果已记录。")
    st.rerun()


def handle_request_release_approval(decision: str, note: str) -> None:
    try:
        request_release_approval(st.session_state.session_id, decision, note)
    except ApiError as exc:
        show_api_error(exc)
        return
    st.success("上线批准决定已记录。")
    st.rerun()


def handle_set_target_deployment(endpoint: str, version: str) -> None:
    if not endpoint.strip() or not version.strip():
        st.error("目标 endpoint 与版本均为必填。")
        return
    try:
        set_target_deployment(
            st.session_state.session_id,
            endpoint.strip(),
            version.strip(),
        )
    except ApiError as exc:
        show_api_error(exc)
        return
    st.warning("目标部署已更新：旧审批与旧测试证据将失效，必须重新评估和测试。")
    st.rerun()


def handle_calibrate_eval_run(
    run_id: str,
    human_label: str,
    human_comment: str,
    disagreement_reason: str = "",
) -> None:
    if human_label == "passed" and not human_comment.strip():
        st.error("判定为 passed 时必须填写人工判定依据。")
        return
    try:
        calibrate_eval_run(
            st.session_state.session_id,
            run_id,
            human_label,
            human_comment.strip(),
            disagreement_reason.strip(),
        )
    except ApiError as exc:
        show_api_error(exc)
        return
    st.success("EvalRun 人工校准已记录。")
    refresh_actions()
    st.rerun()
