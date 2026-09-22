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
    st.info(
        "统计口径：仅统计当前租户的真实业务会话；四个内置场景及其他 "
        "public_demo 演示会话均已排除，不会进入下方指标、趋势或积压动作。"
    )

    # Set Altair theme to handle Chinese display
    alt.themes.register(
        "streamlit",
        lambda: alt.theme.enable(streamlit=False),
    )
    alt.themes.enable("default")

    try:
        response = requests.get(f"{api_base}/governance/overview", headers=headers, timeout=10)
        response.raise_for_status()
        overview = response.json()
    except requests.exceptions.JSONDecodeError:
        st.error("治理总览数据加载失败：接口返回了无法解析的数据。")
        return
    except requests.exceptions.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else "未知"
        st.error(f"治理总览数据加载失败（HTTP {status_code}），这不是正常的空数据状态。")
        return
    except requests.exceptions.RequestException as exc:
        st.error(f"治理总览数据加载失败：无法连接治理接口（{exc}）。")
        return

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("项目数", overview.get("sessions_total", 0))
    col2.metric("待处理动作", overview.get("pending_actions", 0))
    col3.metric("Open 安全发现", overview.get("open_safety_findings", 0))
    col4.metric("已导出报告", overview.get("reports_exported", 0))
    excluded_demo_sessions = overview.get("excluded_demo_sessions", 0)
    st.caption(f"本次统计已隔离 {excluded_demo_sessions} 个内置场景或演示会话。")
    if overview.get("sessions_total", 0) == 0:
        st.info("当前暂无真实业务会话数据；演示会话即使存在，也不会计入治理总览。")

    def _bar_chart_altair(data: dict, ylabel: str = "") -> None:
        """绘制带水平参考线和整数刻度的分布柱状图。"""
        if not data:
            st.info("暂无数据。")
            return

        df = pd.DataFrame(
            {
                "label": list(data.keys()),
                "value": list(data.values()),
            }
        )

        chart = (
            alt.Chart(df)
            .mark_bar(color="#4C8BF5", size=45)
            .encode(
                x=alt.X("label:N", title=None, axis=alt.Axis(labelAngle=0, labelFontSize=12)),
                y=alt.Y(
                    "value:Q",
                    title=ylabel,
                    scale=alt.Scale(zero=True),
                    axis=alt.Axis(
                        labelFontSize=11,
                        tickMinStep=1,
                        grid=True,
                        gridColor="#6B7280",
                        gridOpacity=0.35,
                        gridDash=[3, 3],
                    ),
                ),
                tooltip=[
                    alt.Tooltip("label:N", title="分类"),
                    alt.Tooltip("value:Q", title="数量", format=".0f"),
                ],
            )
            .properties(
                height=300,
                width="container",
            )
            .configure_axis(titleFontSize=12, labelFontSize=11)
            .configure_view(strokeOpacity=0)
        )
        st.altair_chart(chart, use_container_width=True)

    def _line_chart_altair(trend_data: list[dict]) -> None:
        """按固定 0%–100% 量程绘制真实门禁通过率。"""
        if not trend_data:
            st.info("暂无数据。")
            return

        df = pd.DataFrame(
            {
                "week": [item.get("week", "") for item in trend_data],
                "pass_rate": [item.get("pass_rate", 0) for item in trend_data],
                "evaluations": [item.get("evaluations", 0) for item in trend_data],
                "passed": [item.get("passed", 0) for item in trend_data],
            }
        )

        base = (
            alt.Chart(df)
            .encode(
                x=alt.X(
                    "week:N",
                    title="周",
                    sort=None,
                    axis=alt.Axis(labelAngle=0, labelFontSize=12),
                ),
                y=alt.Y(
                    "pass_rate:Q",
                    title="通过率",
                    scale=alt.Scale(domain=[0, 1]),
                    axis=alt.Axis(
                        format=".0%",
                        values=[0, 0.25, 0.5, 0.75, 1],
                        grid=True,
                        gridColor="#6B7280",
                        gridOpacity=0.35,
                        gridDash=[3, 3],
                    ),
                ),
                tooltip=[
                    alt.Tooltip("week:N", title="周"),
                    alt.Tooltip("evaluations:Q", title="评估次数", format=".0f"),
                    alt.Tooltip("passed:Q", title="通过次数", format=".0f"),
                    alt.Tooltip("pass_rate:Q", title="通过率", format=".1%"),
                ],
            )
            .properties(height=280, width="container")
        )
        line = base.mark_line(color="#4C8BF5", strokeWidth=3)
        points = base.mark_point(color="#4C8BF5", filled=True, size=110, stroke="white")

        text_layer = base.mark_text(
            align="center",
            baseline="bottom",
            dy=-12,
            size=12,
            color="white",
        ).encode(
            text=alt.Text("pass_rate:Q", format=".0%"),
        )

        chart = (
            (line + points + text_layer)
            .configure_axis(
                titleFontSize=12,
                labelFontSize=11,
            )
            .configure_view(strokeOpacity=0)
        )
        st.altair_chart(chart, use_container_width=True)

    dist_col1, dist_col2 = st.columns(2)
    with dist_col1:
        st.subheader("会话状态分布")
        state_dist = overview.get("state_distribution", {})
        _bar_chart_altair(_translate_labels(state_dist, SESSION_STATE_LABELS), "数量")

    with dist_col2:
        st.subheader("风险等级分布")
        risk_dist = overview.get("risk_tier_distribution", {})
        _bar_chart_altair(_translate_labels(risk_dist, RISK_TIER_LABELS), "数量")

    st.subheader("门禁通过率趋势（8 周）")
    trends_failed = False
    try:
        response = requests.get(f"{api_base}/governance/gate-trends", headers=headers, timeout=10)
        response.raise_for_status()
        trends = response.json()
    except (requests.exceptions.RequestException, ValueError) as exc:
        st.warning(f"真实业务门禁趋势加载失败：{exc}")
        trends = []
        trends_failed = True

    if trends:
        valid_trends = sorted(
            (item for item in trends if isinstance(item, dict)),
            key=lambda item: item.get("week", ""),
        )
        if len(valid_trends) == 1:
            only = valid_trends[0]
            st.info(
                f"当前仅有 {only.get('week', '本周')} 一个周统计点（评估 "
                f"{only.get('evaluations', 0)} 次，通过 {only.get('passed', 0)} 次），"
                "数据不足以形成趋势线；下图显示该周真实通过率。"
            )
        _line_chart_altair(valid_trends)

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
    elif not trends_failed:
        st.info("暂无门禁趋势数据。")

    st.subheader("积压动作")
    backlog_failed = False
    try:
        response = requests.get(
            f"{api_base}/governance/actions-backlog", headers=headers, timeout=10
        )
        response.raise_for_status()
        backlog = response.json()
    except (requests.exceptions.RequestException, ValueError) as exc:
        st.warning(f"真实业务积压动作加载失败：{exc}")
        backlog = []
        backlog_failed = True
    if backlog:
        st.dataframe(backlog, use_container_width=True)
    elif not backlog_failed:
        st.info("无积压动作。")
