"""治理总览真实数据口径与错误提示的前端契约测试。"""

from __future__ import annotations

from pathlib import Path

COMPONENT_PATH = (
    Path(__file__).resolve().parent.parent / "frontend" / "components" / "governance_overview.py"
)
SOURCE = COMPONENT_PATH.read_text(encoding="utf-8")


def test_governance_page_explicitly_marks_real_business_scope() -> None:
    assert "仅统计当前租户的真实业务会话" in SOURCE
    assert "四个内置场景" in SOURCE
    assert "public_demo 演示会话均已排除" in SOURCE
    assert "本次统计已隔离" in SOURCE


def test_governance_page_distinguishes_empty_data_from_request_failure() -> None:
    assert "response.raise_for_status()" in SOURCE
    assert "这不是正常的空数据状态" in SOURCE
    assert "当前暂无真实业务会话数据" in SOURCE
    assert "演示会话即使存在，也不会计入治理总览" in SOURCE


def test_governance_charts_keep_axes_readable_for_sparse_real_data() -> None:
    assert "tickMinStep=1" in SOURCE
    assert "grid=True" in SOURCE
    assert 'gridColor="#6B7280"' in SOURCE
    assert "scale=alt.Scale(domain=[0, 1])" in SOURCE
    assert 'format=".0%"' in SOURCE
    assert "size=110" in SOURCE
    assert "数据不足以形成趋势线" in SOURCE
    assert "valid_trends = sorted(" in SOURCE
