# frontend/controllers/governance_controller.py
from __future__ import annotations

import json

import streamlit as st
from models.api_client import (
    resolve_action,
    resolve_flag,
    resolve_safety_finding,
    verify_evidence,
)
from models.session_state import refresh_actions, refresh_flags


def handle_verify_action(action_id: str, note: str) -> None:
    if resolve_action(
        st.session_state.session_id,
        action_id,
        "verify_evidence",
        note,
    ):
        refresh_flags()
        refresh_actions()
        st.rerun()


def handle_dismiss_action(action_id: str, note: str) -> None:
    if resolve_action(st.session_state.session_id, action_id, "dismissed", note):
        refresh_flags()
        refresh_actions()
        st.warning(
            "已忽略并留痕，但高风险证据门控可能仍未解除。"
            "请查看左侧「阶段推进阻断器」确认是否仍被阻断。"
        )
        st.rerun()


def handle_approve_action(action_id: str, note: str) -> None:
    if resolve_action(st.session_state.session_id, action_id, "approve", note):
        refresh_flags()
        refresh_actions()
        st.rerun()


def handle_reject_action(action_id: str, note: str) -> None:
    if resolve_action(st.session_state.session_id, action_id, "reject", note):
        refresh_flags()
        refresh_actions()
        st.warning("该关键动作已驳回。请使用聊天区输入「修改」或「回退」后再继续。")
        st.rerun()


def handle_escalate_action(action_id: str, note: str) -> None:
    if resolve_action(st.session_state.session_id, action_id, "approve", note):
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


def handle_edit_reject_action(action_id: str, note: str) -> None:
    if resolve_action(st.session_state.session_id, action_id, "reject", note):
        refresh_flags()
        refresh_actions()
        st.warning("该编辑动作已驳回。请使用「修改」或「回退」重新生成。")
        st.rerun()


def handle_verify_flag(flag_id: str, note: str) -> None:
    if resolve_flag(
        st.session_state.session_id,
        flag_id,
        "verified",
        note,
    ):
        st.session_state.pending_flags = [
            f for f in st.session_state.pending_flags if f["item_id"] != flag_id
        ]
        st.rerun()


def handle_dismiss_flag(flag_id: str, note: str) -> None:
    if resolve_flag(
        st.session_state.session_id,
        flag_id,
        "dismissed",
        note,
    ):
        st.session_state.pending_flags = [
            f for f in st.session_state.pending_flags if f["item_id"] != flag_id
        ]
        st.rerun()


def handle_verify_evidence_item(evidence_id: str, note: str) -> None:
    if verify_evidence(st.session_state.session_id, evidence_id, note):
        refresh_actions()
        st.success("证据已核验；若有关联的低可信证据动作，会自动关闭。")
        st.rerun()


def handle_resolve_safety_item(finding_id: str, note: str) -> None:
    if resolve_safety_finding(
        st.session_state.session_id,
        finding_id,
        "resolved",
        note,
    ):
        refresh_actions()
        st.rerun()


def handle_dismiss_safety_item(finding_id: str, note: str) -> None:
    if resolve_safety_finding(
        st.session_state.session_id,
        finding_id,
        "dismissed",
        note,
    ):
        refresh_actions()
        st.rerun()
