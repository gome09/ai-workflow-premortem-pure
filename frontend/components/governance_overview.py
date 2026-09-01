from __future__ import annotations

# 会话状态英文枚举 → 中文展示
SESSION_STATE_LABELS = {
    "init": "初始化",
    "s1_running": "阶段1执行中",
    "s1_review": "阶段1审核",
    "s2_running": "阶段2执行中",
    "s2_review": "阶段2审核",
    "s3_running": "阶段3执行中",
    "s3_review": "阶段3审核",
    "s4_running": "阶段4执行中",
    "s4_review": "阶段4审核",
    "iterating": "迭代中",
    "complete": "已完成",
}

# 风险等级英文枚举 → 中文展示
RISK_TIER_LABELS = {
    "low": "低",
    "medium": "中",
    "high": "高",
    "critical": "极高",
}


def _translate_labels(data: dict, label_map: dict) -> dict:
    """将分布数据的键替换为中文标签；未知键保持原值。"""
    return {label_map.get(k, k): v for k, v in data.items()}


def render_governance_overview(api_base: str, token: str) -> None:
    """治理总览页：指标卡片 + 状态/风险分布 + 通过率趋势 + 积压动作表。"""
    import altair as alt
    import pandas as pd
    import requests
    import streamlit as st

    headers = {"Authorization": f"Bearer {token}"}
    st.header("治理总览")

    # Set Altair theme to handle Chinese display
    alt.themes.register(
        "streamlit",
        lambda: alt.theme.enable(streamlit=False),
    )
    alt.themes.enable("default")

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

    def _bar_chart_altair(data: dict, title: str, ylabel: str = "") -> None:
        """Create a bar chart with horizontal x-axis labels using altair."""
        if not data:
            st.info("暂无数据。")
            return

        df = pd.DataFrame({
            "label": list(data.keys()),
            "value": list(data.values()),
        })

        chart = (
            alt.Chart(df)
            .mark_bar(color="#4C8BF5", size=45)
            .encode(
                x=alt.X("label:N", title=None, axis=alt.Axis(labelAngle=0, labelFontSize=12)),
                y=alt.Y("value:Q", title=ylabel, axis=alt.Axis(labelFontSize=11)),
                text=alt.Text("value:Q", format=".0f"),
            )
            .properties(
                title=title,
                height=300,
                width="container",
            )
            .configure_title(fontSize=16, anchor="start")
            .configure_axis(grid=False, titleFontSize=12, labelFontSize=11)
            .configure_view(strokeOpacity=0)
        )
        st.altair_chart(chart, use_container_width=True)

    def _line_chart_altair(
        x_data: list, y_data: list, title: str, xlabel: str = "", ylabel: str = ""
    ) -> None:
        """Create a line chart with horizontal x-axis labels using altair."""
        if not x_data or not y_data:
            st.info("暂无数据。")
            return

        df = pd.DataFrame({
            "x": x_data,
            "y": y_data,
        })

        max_y = max(y_data) * 1.2 if y_data else 1

        chart = (
            alt.Chart(df)
            .mark_line(color="#4C8BF5", point={"filled": True, "size": 12})
            .encode(
                x=alt.X("x:N", title=xlabel, axis=alt.Axis(labelAngle=0, labelFontSize=12)),
                y=alt.Y("y:Q", title=ylabel, scale=alt.Scale(domain=[0, max_y])),
            )
            .properties(
                title=title,
                height=340,
                width="container",
            )
        )

        # Add text labels on points using layer
        text_layer = alt.Chart(df).mark_text(
            align="center",
            baseline="bottom",
            dy=-15,
            size=11,
            color="white",
        ).encode(
            x="x:N",
            y=alt.Y("y:Q", scale=alt.Scale(domain=[0, max_y])),
            text=alt.Text("y:Q", format=".2f"),
        )

        (chart + text_layer).configure_title(
            fontSize=16, anchor="start"
        ).configure_axis(
            grid=False,
            titleFontSize=12,
            labelFontSize=11,
        ).configure_view(strokeOpacity=0)

        st.altair_chart(chart + text_layer, use_container_width=True)

    dist_col1, dist_col2 = st.columns(2)
    with dist_col1:
        st.subheader("会话状态分布")
        state_dist = overview.get("state_distribution", {})
        _bar_chart_altair(
            _translate_labels(state_dist, SESSION_STATE_LABELS), "会话状态分布", "数量"
        )

    with dist_col2:
        st.subheader("风险等级分布")
        risk_dist = overview.get("risk_tier_distribution", {})
        _bar_chart_altair(_translate_labels(risk_dist, RISK_TIER_LABELS), "风险等级分布", "数量")

    st.subheader("门禁通过率趋势（8 周）")
    try:
        trends = requests.get(
            f"{api_base}/governance/gate-trends", headers=headers, timeout=10
        ).json()
    except requests.exceptions.RequestException:
        trends = []

    if trends:
        weeks = [t.get("week", "") if isinstance(t, dict) else str(t) for t in trends]
        pass_rates = [t.get("pass_rate", 0) if isinstance(t, dict) else 0 for t in trends]
        _line_chart_altair(weeks, pass_rates, "门禁通过率趋势（8 周）", "周", "通过率")

        with st.expander("每周明细（评估次数 / Top 阻断规则）"):
            for t in trends:
                if not isinstance(t, dict):
                    continue
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
