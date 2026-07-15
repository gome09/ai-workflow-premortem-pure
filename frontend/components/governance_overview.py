from __future__ import annotations


def render_governance_overview(api_base: str, token: str) -> None:
    """治理总览页：三张卡片 + 风险分布 + 通过率趋势 + 积压动作表。"""
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

    col1, col2, col3 = st.columns(3)
    col1.metric("项目数", overview.get("sessions_total", 0))
    col2.metric("待处理动作", overview.get("pending_actions", 0))
    col3.metric("Open 安全发现", overview.get("open_safety_findings", 0))

    st.subheader("风险等级分布")
    risk_dist = overview.get("risk_tier_distribution", {})
    if risk_dist:
        st.bar_chart(risk_dist)
    else:
        st.info("暂无风险等级数据。")
    st.caption(
        "ℹ️ 领域风险下限说明：HIGH/CRITICAL 领域（如医疗、金融、心理健康等）"
        "的风险等级不会被低风险用途词（如「个人」「演示」）下调。"
        "低风险用途词不影响 HIGH/CRITICAL 领域风险下限。"
    )

    st.subheader("门禁通过率趋势（8 周）")
    try:
        trends = requests.get(
            f"{api_base}/governance/gate-trends", headers=headers, timeout=10
        ).json()
    except requests.exceptions.RequestException:
        trends = []
    if trends:
        st.line_chart(
            [{"week": t.get("week", ""), "通过率": t.get("pass_rate", 0)} for t in trends]
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
