# frontend/views/panels/closure_panel.py
"""Business closure: evidence lifecycle, risk treatments, release approval."""

from __future__ import annotations

from collections import Counter

import streamlit as st
from controllers.governance_controller import (
    handle_request_release_approval,
    handle_review_treatment,
    handle_upsert_treatment,
)
from labels import (
    approval_status_zh,
    evidence_lifecycle_zh,
    treatment_status_zh,
)
from models.api_client import (
    get_approval_status,
    list_evidence,
    list_risk_treatments,
)

_TREATMENT_STATUSES = ["planned", "in_progress", "completed", "accepted"]


def _session_id() -> str:
    return getattr(st.session_state, "session_id", "") or ""


def render_closure_panel() -> None:
    session_id = _session_id()
    if not session_id:
        return

    with st.expander("业务闭环：证据 / 风险处置 / 上线批准", expanded=False):
        _render_evidence_lifecycle(session_id)
        st.divider()
        _render_risk_treatments(session_id)
        st.divider()
        _render_release_approval(session_id)


def _render_evidence_lifecycle(session_id: str) -> None:
    st.markdown("#### 证据生命周期")
    evidence = list_evidence(session_id)
    if not evidence:
        st.caption("暂无证据来源。")
        return
    counts = Counter(item.get("lifecycle_status", "submitted") for item in evidence)
    col1, col2, col3 = st.columns(3)
    col1.metric("已提交（未核验）", counts.get("submitted", 0))
    col2.metric("已核验", counts.get("verified", 0))
    col3.metric("已采纳（关联风险）", counts.get("adopted", 0))
    for item in evidence[:10]:
        st.caption(
            f"- `{item.get('evidence_id')}` "
            f"{evidence_lifecycle_zh(item.get('lifecycle_status'))} · "
            f"来源={item.get('source_type')} · 核验人={item.get('verified_by') or '-'} · "
            f"关联风险={', '.join(item.get('used_by_failure_mode_ids') or []) or '-'}"
        )


def _render_risk_treatments(session_id: str) -> None:
    st.markdown("#### 风险处置")
    payload = list_risk_treatments(session_id)
    if not payload.get("applicable", True):
        st.info("public_demo 演示会话不适用风险处置门禁。")
        return

    summary = payload.get("summary") or {}
    col1, col2 = st.columns(2)
    col1.metric("高风险项", summary.get("requirements_total", 0))
    col2.metric("已闭环", summary.get("complete_count", 0))

    items = payload.get("items") or []
    if not items:
        st.caption("当前没有 high/critical 风险项需要处置。")
        return

    for index, item in enumerate(items):
        requirement = item.get("requirement") or {}
        treatment = item.get("treatment") or {}
        state = item.get("state") or "missing"
        label = (
            f"{requirement.get('source_type')}/{requirement.get('source_id')} · "
            f"{state} · {treatment.get('owner') or '未指定责任人'}"
        )
        with st.expander(label, expanded=False):
            st.caption(requirement.get("description") or "")
            owner = st.text_input(
                "责任人",
                value=treatment.get("owner") or "",
                key=f"closure_owner_{index}",
            )
            plan = st.text_area(
                "缓解措施",
                value=treatment.get("mitigation_plan") or "",
                key=f"closure_plan_{index}",
                height=90,
            )
            current_status = treatment.get("status") or "planned"
            status_index = (
                _TREATMENT_STATUSES.index(current_status)
                if current_status in _TREATMENT_STATUSES
                else 0
            )
            status = st.selectbox(
                "执行状态",
                _TREATMENT_STATUSES,
                index=status_index,
                key=f"closure_status_{index}",
                format_func=treatment_status_zh,
            )
            note = st.text_input("处置备注", key=f"closure_note_{index}")
            if st.button("保存处置", key=f"closure_save_{index}", use_container_width=True):
                handle_upsert_treatment(
                    requirement.get("source_type") or "",
                    requirement.get("source_id") or "",
                    owner,
                    plan,
                    status,
                    note,
                )

            treatment_id = treatment.get("treatment_id") or ""
            if treatment_id and treatment.get("status") in {"completed", "accepted"}:
                st.caption(f"复核状态：{treatment.get('reviewed_by') or '尚未复核'}")
                review_note = st.text_input("复核备注", key=f"closure_review_note_{index}")
                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button(
                        "复核通过",
                        key=f"closure_accept_{index}",
                        use_container_width=True,
                    ):
                        handle_review_treatment(treatment_id, "accept", review_note)
                with col_b:
                    if st.button(
                        "驳回复核",
                        key=f"closure_reject_{index}",
                        use_container_width=True,
                    ):
                        handle_review_treatment(treatment_id, "reject", review_note)


def _render_release_approval(session_id: str) -> None:
    st.markdown("#### 上线批准")
    status_payload = get_approval_status(session_id)
    summary = status_payload.get("approval_summary") or {}
    readiness = status_payload.get("release_readiness") or {}

    report_generation = summary.get("report_generation") or {}
    evaluation_completion = summary.get("evaluation_completion") or {}
    release_approval = summary.get("release_approval") or {}

    st.caption(
        f"报告生成：{report_generation.get('artifact_count', 0)} 份（报告可导出 ≠ 审批通过）"
    )
    st.caption(f"评估完成：{evaluation_completion.get('completed')}")
    st.caption(
        "上线批准："
        f"{approval_status_zh(release_approval.get('status'))} · "
        f"批准人={release_approval.get('decided_by') or '-'}"
    )
    if release_approval.get("stale_reason"):
        st.warning(f"审批已失效：{release_approval.get('stale_reason')}")

    blockers = readiness.get("blockers") or []
    if blockers:
        st.markdown("**上线前置条件未满足：**")
        for blocker in blockers[:10]:
            st.text(f"- {blocker.get('code')}：{blocker.get('message')}")

    note = st.text_input("审批备注", key="release_approval_note")
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button(
            "批准上线",
            key="release_approve_button",
            use_container_width=True,
            disabled=not bool(readiness.get("can_approve")),
        ):
            handle_request_release_approval("approve", note)
    with col_b:
        if st.button(
            "驳回上线",
            key="release_reject_button",
            use_container_width=True,
        ):
            handle_request_release_approval("reject", note)
