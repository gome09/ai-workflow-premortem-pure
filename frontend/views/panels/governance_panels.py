# frontend/views/panels/governance_panels.py
from __future__ import annotations

import streamlit as st
from controllers.governance_controller import (
    handle_approve_action,
    handle_dismiss_action,
    handle_dismiss_flag,
    handle_dismiss_safety_item,
    handle_edit_action,
    handle_edit_reject_action,
    handle_escalate_action,
    handle_reject_action,
    handle_resolve_safety_item,
    handle_verify_action,
    handle_verify_evidence_item,
    handle_verify_flag,
)
from labels import resolution_zh, risk_type_zh, severity_zh
from models.api_client import list_evidence, list_safety_findings
from models.mappings import STRUCTURED_EDIT_SOURCE_TYPES


def render_action_queue() -> None:
    """Human Oversight 动作队列。"""
    # 动作队列直接读取派生状态；pending_actions 由 select/send/mutation/刷新按钮写入，
    # 不在每次 rerun 时无条件重拉接口。
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
                f"[阶段{action.get('stage_id')} v{version}] "
                f"{severity_zh(risk)}/{resolution_zh(action_type)}/{blocking} · {title}",
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
                    st.caption(
                        "⚠️ 「忽略并留痕」只会关闭这条动作并记录留痕，"
                        "**不会**解除高风险证据门控；若要真正解除门控，"
                        "请点击「已核验」，或按需通过「修改」编辑结构化输出补充/修正证据引用。"
                    )
                    col_a, col_b = st.columns(2)
                    with col_a:
                        if st.button(
                            "✅ 已核验",
                            key=f"verify_action_{action_id}",
                            use_container_width=True,
                        ):
                            handle_verify_action(action_id, note)
                    with col_b:
                        if st.button(
                            "❌ 忽略并留痕",
                            key=f"dismiss_action_{action_id}",
                            use_container_width=True,
                        ):
                            handle_dismiss_action(action_id, note)

                elif action_type == "approve":
                    col_a, col_b = st.columns(2)
                    with col_a:
                        if st.button(
                            "✅ 批准继续",
                            key=f"approve_action_{action_id}",
                            use_container_width=True,
                        ):
                            handle_approve_action(action_id, note)
                    with col_b:
                        if st.button(
                            "❌ 驳回并要求修改",
                            key=f"reject_action_{action_id}",
                            use_container_width=True,
                        ):
                            handle_reject_action(action_id, note)

                elif action_type == "escalate":
                    st.warning(
                        "该动作属于 critical/escalate，必须明确批准或回退修改，不能忽略关闭。"
                    )
                    if st.button(
                        "🧑‍⚖️ 升级风险已明确批准",
                        key=f"escalate_approve_{action_id}",
                        use_container_width=True,
                    ):
                        handle_escalate_action(action_id, note)

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
                            handle_edit_action(
                                action_id,
                                note,
                                edit_text,
                                structured_text,
                                structured_required,
                            )
                    with col_b:
                        if st.button(
                            "❌ 驳回，需重跑",
                            key=f"edit_reject_{action_id}",
                            use_container_width=True,
                        ):
                            handle_edit_reject_action(action_id, note)


def render_flags_panel() -> None:
    """【需核验】面板。"""
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
                        handle_verify_flag(flag["item_id"], note)
                with btn_col2:
                    if st.button(
                        "❌ 忽略",
                        key=f"dismiss_{flag['item_id']}",
                        use_container_width=True,
                    ):
                        handle_dismiss_flag(flag["item_id"], note)


def render_evidence_panel() -> None:
    with st.expander("📚 证据来源", expanded=False):
        evidence_items = list_evidence(st.session_state.session_id)
        if evidence_items:
            verified_total = sum(1 for e in evidence_items if e.get("verified"))
            st.caption(
                f"共 {len(evidence_items)} 条 · "
                f"已核验 {verified_total} 条 · "
                f"未核验 {len(evidence_items) - verified_total} 条"
            )
            for ev in evidence_items:
                verified = ev.get("verified", False)
                score = ev.get("credibility_score", 0.0)
                status_icon = "✅" if verified else "⚪"
                status_text = "已核验" if verified else "未核验"
                st.markdown(
                    f"{status_icon} **`{ev.get('evidence_id')}`** · "
                    f"{ev.get('source_type')} · "
                    f"可信度={score:.2f} · {status_text}"
                )
                st.caption(ev.get("title", ""))
                if ev.get("url"):
                    st.caption(ev.get("url"))
                if ev.get("summary"):
                    st.caption(ev["summary"][:200])
                claims = ev.get("claims") or []
                if claims:
                    with st.expander(f"论据（{len(claims)}）", expanded=False):
                        for claim in claims:
                            st.markdown(f"- {claim}")
                if ev.get("used_by_failure_mode_ids"):
                    st.caption("关联失败模式：" + "、".join(ev.get("used_by_failure_mode_ids", [])))
                if verified and ev.get("verification_note"):
                    st.caption(f"核验备注：{ev['verification_note']}")
                if not verified and score < 0.4:
                    st.warning("可信度较低——未核验的弱来源可能削弱后续分析的可靠性。")
                note_key = f"evidence_note_{ev.get('evidence_id')}"
                ev_note = st.text_input("核验备注", key=note_key)
                if not verified:
                    if st.button(
                        "✅ 核验证据",
                        key=f"verify_ev_{ev.get('evidence_id')}",
                        use_container_width=True,
                    ):
                        handle_verify_evidence_item(ev.get("evidence_id"), ev_note)
                st.divider()
        else:
            st.caption("暂无证据来源。阶段一搜索完成后会自动生成。")


def render_safety_panel() -> None:
    with st.expander("🛡️ 安全风险发现", expanded=False):
        findings = list_safety_findings(st.session_state.session_id, status="open")
        if findings:
            high_crit_open = sum(
                1
                for f in findings
                if f.get("status") == "open" and f.get("severity") in {"high", "critical"}
            )
            st.caption(f"待处理 {len(findings)} 项 · 高危/危急未处理 {high_crit_open} 项")
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
                    f"{severity_icon} **`{finding.get('finding_id')}`** · 阶段{finding.get('stage_id')} · "
                    f"{severity_zh(severity)} / {risk_type_zh(finding.get('risk_type'))}"
                )
                st.caption(finding.get("description", ""))
                st.caption("建议处理：" + finding.get("recommended_action", ""))
                if is_high_crit:
                    st.warning("高危 / 危急安全发现尚未处理——可能阻断阶段推进或需要人工复核。")
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
                        handle_resolve_safety_item(finding.get("finding_id"), finding_note)
                else:
                    col_resolve, col_dismiss = st.columns(2)
                    with col_resolve:
                        if st.button(
                            "✅ 已处理",
                            key=f"resolve_safety_{finding.get('finding_id')}",
                            use_container_width=True,
                        ):
                            handle_resolve_safety_item(finding.get("finding_id"), finding_note)
                    with col_dismiss:
                        if st.button(
                            "📝 忽略留痕",
                            key=f"dismiss_safety_{finding.get('finding_id')}",
                            use_container_width=True,
                        ):
                            handle_dismiss_safety_item(finding.get("finding_id"), finding_note)
                st.divider()
        else:
            st.caption("暂无未关闭安全发现。")
