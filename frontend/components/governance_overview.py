from __future__ import annotations


def render_governance_overview(api_base: str, token: str) -> None:
    """治理总览页：指标卡片 + 状态/风险分布 + 通过率趋势 + 积压动作表。"""
    import pandas as pd
    import requests
    import streamlit as st

    headers = {"Authorization": f"Bearer {token}"}
    st.header("治理总览")

    try:
        overview = requests.get(
            f"{api_base}/governance/overview", headers=headers, timeout=10
        ).json()
    except requests.exceptions.RequestException:
        st.error("无法获取治理总览数据。")
        return

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("项目数", overview.get("sessions_total", 0))
    col2.metric("待处理动作", overview.get("pending_actions", 0))
    col3.metric("Open 安全发现", overview.get("open_safety_findings", 0))
    col4.metric("已导出报告", overview.get("reports_exported", 0))

    dist_col1, dist_col2 = st.columns(2)
    with dist_col1:
        st.subheader("会话状态分布")
        state_dist = overview.get("state_distribution", {})
        if state_dist:
            st.bar_chart(state_dist)
        else:
            st.info("暂无会话状态数据。")
    with dist_col2:
        st.subheader("风险等级分布")
        risk_dist = overview.get("risk_tier_distribution", {})
        if risk_dist:
            st.bar_chart(risk_dist)
        else:
            st.info("暂无风险等级数据。")

    st.subheader("门禁通过率趋势（8 周）")
    try:
        trends = requests.get(
            f"{api_base}/governance/gate-trends", headers=headers, timeout=10
        ).json()
    except requests.exceptions.RequestException:
        trends = []
    if trends:
        trend_df = pd.DataFrame(
            {
                "week": [t.get("week", "") for t in trends],
                "通过率": [t.get("pass_rate", 0) for t in trends],
            }
        ).set_index("week")
        st.line_chart(trend_df)
        with st.expander("每周明细（评估次数 / Top 阻断规则）"):
            for t in trends:
                top_rules = (
                    ", ".join(
                        f"{r.get('rule_id')}×{r.get('count')}"
                        for r in t.get("top_blocking_rules", [])
                    )
                    or "无"
                )
                st.caption(
                    f"{t.get('week')} · 评估 {t.get('evaluations', 0)} 次 · "
                    f"通过 {t.get('passed', 0)} 次 · Top 阻断规则：{top_rules}"
                )
    else:
        st.info("暂无门禁趋势数据。")

    st.subheader("积压动作")
    try:
        backlog = requests.get(
            f"{api_base}/governance/actions-backlog", headers=headers, timeout=10
        ).json()
    except requests.exceptions.RequestException:
        backlog = []
    if backlog:
        st.dataframe(backlog, use_container_width=True)
    else:
        st.info("无积压动作。")
