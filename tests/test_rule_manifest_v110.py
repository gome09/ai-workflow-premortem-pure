# tests/test_rule_manifest_v110.py
"""T3.1 门禁规则元数据清单（manifest）契约测试。

校验 RULE_MANIFEST 与注册规则实现之间的双向完整性，以及 RuleMeta 字段
语义化版本/rationale/standard_refs/safety_bottom_line 等不变量。
"""

from __future__ import annotations

import re

import pytest

from core.gates.rules import registered_rules
from core.gates.rules.manifest import (
    RULE_MANIFEST,
    get_rule_meta,
    get_rule_version,
    is_safety_bottom_line,
)

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def _implemented_rule_ids() -> set[str]:
    return {rule.rule_id for rule in registered_rules()}


def test_all_registered_rules_have_manifest_entry():
    """每条注册规则在 RULE_MANIFEST 都有条目。"""
    missing = _implemented_rule_ids() - set(RULE_MANIFEST.keys())
    assert missing == set(), f"registered rules without manifest: {sorted(missing)}"


def test_all_manifest_entries_have_implementation():
    """每个 manifest 条目都有对应实现（双向完整性）。"""
    missing = set(RULE_MANIFEST.keys()) - _implemented_rule_ids()
    assert missing == set(), f"manifest entries without implementation: {sorted(missing)}"


def test_registered_rules_count_is_fourteen():
    """契约：当前共 14 条门禁规则（含 cross_stage_integrity）。"""
    assert len(_implemented_rule_ids()) == 14
    assert len(RULE_MANIFEST) == 14


@pytest.mark.parametrize("rule_id", sorted(RULE_MANIFEST.keys()))
def test_version_is_semver(rule_id):
    assert SEMVER_RE.match(RULE_MANIFEST[rule_id].version), (
        f"{rule_id}: version {RULE_MANIFEST[rule_id].version!r} 不符合 semver"
    )


@pytest.mark.parametrize("rule_id", sorted(RULE_MANIFEST.keys()))
def test_rationale_nonempty(rule_id):
    assert RULE_MANIFEST[rule_id].rationale.strip(), f"{rule_id}: rationale 为空"


@pytest.mark.parametrize("rule_id", sorted(RULE_MANIFEST.keys()))
def test_standard_refs_contain_colon(rule_id):
    refs = RULE_MANIFEST[rule_id].standard_refs
    assert refs, f"{rule_id}: standard_refs 为空"
    for ref in refs:
        assert ":" in ref, f"{rule_id}: standard_ref {ref!r} 缺少 ':' 分隔符"


def test_safety_bottom_line_flags():
    assert is_safety_bottom_line("missing_output") is True
    assert is_safety_bottom_line("redteam_coverage") is False


def test_get_rule_version_redteam_coverage():
    assert get_rule_version("redteam_coverage") == "1.1.0"


def test_get_rule_meta_nonexistent_returns_none():
    assert get_rule_meta("nonexistent") is None


def test_get_rule_version_unknown_is_zero():
    assert get_rule_version("nonexistent") == "0.0.0"


def test_safety_bottom_line_rules_exactly_eight():
    """safety_bottom_line=True 的规则恰好是 8 条（含 cross_stage_integrity）。"""
    expected = {
        "missing_output",
        "stale_dependency",
        "action_state",
        "parser_error",
        "safety_finding",
        "stage4_final_governance",
        "expert_review",
        "cross_stage_integrity",
    }
    actual = {rid for rid, meta in RULE_MANIFEST.items() if meta.safety_bottom_line}
    assert actual == expected
    assert len(actual) == 8
