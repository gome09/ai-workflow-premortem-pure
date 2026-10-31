# frontend/views/panels/diagnostics_panel.py
from __future__ import annotations

import streamlit as st
from models.api_client import get_health, list_audit_events


def render_interrupt_panel() -> None:
    with st.expander("🧩 执行 / 中断调试", expanded=False):
        # interrupt_records 由 select/mutation/刷新按钮写入；空列表是有效结果，
        # 不再用 falsy 判断触发第二次请求。
        records = st.session_state.interrupt_records
        health = st.session_state.health or get_health()
        st.caption(
            "默认 single_step 保持稳定；"
            "启用 WORKFLOW_EXECUTION_MODE=langgraph_interrupt 后使用 checkpoint-backed interrupt/resume；"
            "action/interrupt 同步由执行协调层处理。"
        )
        if health:
            st.caption(
                f"执行模式：`{health.get('workflow_execution_mode', 'unknown')}` · "
                f"中断适配器状态：`{health.get('interrupt_adapter_status', 'unknown')}`"
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
                    if record.get("status") == "resumed" and not record.get("resume_consumed_at"):
                        st.warning("该 interrupt 已标记 resumed，但 Command(resume=...) 尚未消费。")
                    elif record.get("status") == "cancelled":
                        st.info("该 interrupt 已取消，不会恢复执行。")
                    elif record.get("resume_consumed_at"):
                        st.success(f"恢复消费时间：{record.get('resume_consumed_at')}")
                    st.json(record)
        else:
            st.caption(
                "暂无 interrupt records。阻断型 PendingHumanAction 出现后会自动创建映射记录。"
            )


def render_audit_panel() -> None:
    with st.expander("🧾 审计历史", expanded=False):
        events = list_audit_events(st.session_state.session_id)
        if events:
            st.caption(f"共记录 {len(events)} 条审计事件（显示最近 30 条）")
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
                    st.caption(f"事件类型：**{event_type}**")
                    st.caption(f"操作者：{actor}  ·  时间：{created_at}")
                    st.caption(f"目标对象：{target_type}/{target_id}")
                    if metadata:
                        with st.expander("元数据", expanded=False):
                            st.json(metadata)
                    before_snapshot = event.get("before_snapshot")
                    after_snapshot = event.get("after_snapshot")
                    if before_snapshot or after_snapshot:
                        with st.expander("变更前后快照", expanded=False):
                            snap_before, snap_after = st.columns(2)
                            with snap_before:
                                st.caption("变更前")
                                st.json(before_snapshot or {})
                            with snap_after:
                                st.caption("变更后")
                                st.json(after_snapshot or {})
        else:
            st.caption("暂无审计事件。")
