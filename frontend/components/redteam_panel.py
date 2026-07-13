# frontend/components/redteam_panel.py
from __future__ import annotations

import streamlit as st


def render_redteam_panel(*, cases: list[dict], coverage: dict) -> None:
    """红队覆盖精简面板。"""

    st.subheader("红队覆盖")
    st.caption(
        "阶段三推进前，红队用例草稿必须先批准、同步为评测用例，"
        "并归入一个红队生成的评测数据集。"
    )
    cols = st.columns(4)
    cols[0].metric("红队用例", coverage.get("total_cases", len(cases)))
    cols[1].metric("草稿", coverage.get("draft_cases", 0))
    cols[2].metric("已批准", coverage.get("approved_cases", 0))
    cols[3].metric("已同步", coverage.get("synced_cases", 0))

    if coverage.get("blocking"):
        st.warning("红队覆盖当前正在阻断阶段三推进。")
    else:
        st.success("红队覆盖门控当前没有阻断项。")

    gaps = {
        "缺少安全发现覆盖": coverage.get("missing_safety_finding_ids") or [],
        "缺少节点覆盖": coverage.get("missing_node_ids") or [],
        "高风险草稿用例": coverage.get("draft_high_case_ids") or [],
        "已批准但未同步的用例": coverage.get("approved_unsynced_case_ids") or [],
        "已同步但不在红队数据集中的评测用例": coverage.get(
            "synced_eval_ids_without_redteam_dataset"
        )
        or [],
    }
    for label, values in gaps.items():
        if values:
            st.caption(f"{label}：{', '.join(values)}")

    for case in cases:
        with st.expander(
            f"{case.get('status')} · {case.get('redteam_case_id')} · {case.get('attack_type')}",
            expanded=False,
        ):
            st.caption(
                f"严重程度={case.get('severity')} · 目标节点={case.get('target_node_id') or '-'} · "
                f"安全发现={case.get('source_finding_id') or '-'} · 失败模式={case.get('source_failure_mode_id') or '-'}"
            )
            st.markdown("**攻击提示词**")
            st.write(case.get("prompt") or "")
            st.markdown("**期望的安全行为**")
            st.write(case.get("expected_safe_behavior") or "")
            if case.get("taxonomy_refs"):
                st.caption("分类引用=" + "、".join(case.get("taxonomy_refs") or []))
            if case.get("control_refs"):
                st.caption("控制项引用=" + "、".join(case.get("control_refs") or []))
            if case.get("linked_eval_case_id"):
                st.caption(f"关联评测用例={case.get('linked_eval_case_id')}")
