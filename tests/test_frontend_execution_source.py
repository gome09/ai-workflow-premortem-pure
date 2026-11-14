# tests/test_frontend_execution_source.py
"""实验"实际执行来源"只汇总同一 experiment_id 的运行，不虚报真实执行。"""

from __future__ import annotations

import ast
from pathlib import Path

LABELS_PATH = Path(__file__).resolve().parent.parent / "frontend" / "labels.py"
LABELS_SOURCE = LABELS_PATH.read_text(encoding="utf-8")


def _labels_ns() -> dict:
    tree = ast.parse(LABELS_SOURCE)
    wanted_functions = {"zh", "execution_kind_zh", "experiment_execution_source_zh", "verifier_zh"}
    wanted_assigns = {"EXECUTION_KIND_ZH"}
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in wanted_functions:
            nodes.append(node)
        elif (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in wanted_assigns
        ):
            nodes.append(node)
    namespace = {"__builtins__": __builtins__}
    exec(  # noqa: S102 — 执行本仓库前端抽取出的受控源码
        compile(ast.Module(body=nodes, type_ignores=[]), str(LABELS_PATH), "exec"),
        namespace,
    )
    return namespace


def _source(runs, experiment_id="EXP-1", runs_available=True):
    return _labels_ns()["experiment_execution_source_zh"](
        runs, experiment_id, runs_available=runs_available
    )


def test_runs_unavailable_is_explicit_unknown():
    assert _source([], runs_available=False) == "未知（运行列表读取失败）"


def test_no_matching_run_is_not_started():
    assert _source([]) == "尚未执行"
    assert _source([{"experiment_id": "EXP-2", "execution_kind": "real_target_execution"}]) == (
        "尚未执行"
    )


def test_single_execution_kind_uses_chinese_label():
    runs = [
        {"experiment_id": "EXP-1", "execution_kind": "dry_run_simulation"},
        {"experiment_id": "EXP-1", "execution_kind": "dry_run_simulation"},
    ]
    assert _source(runs) == "演练模拟"


def test_mixed_execution_kinds_are_reported_as_mixed():
    runs = [
        {"experiment_id": "EXP-1", "execution_kind": "dry_run_simulation"},
        {"experiment_id": "EXP-1", "execution_kind": "real_target_execution"},
    ]
    message = _source(runs)
    assert message.startswith("混合（")
    assert "演练模拟" in message and "真实目标执行" in message


def test_missing_kind_falls_back_to_unique_run_mode():
    runs = [{"experiment_id": "EXP-1", "run_mode": "llm_node", "execution_kind": ""}]
    assert _source(runs) == "llm_node（来源未记录）"


def test_partial_kind_is_mixed_not_overclaimed():
    runs = [
        {"experiment_id": "EXP-1", "execution_kind": "dry_run_simulation"},
        {"experiment_id": "EXP-1", "execution_kind": ""},
    ]
    message = _source(runs)
    assert "来源未记录" in message
    assert message.startswith("混合（")


def test_no_kind_and_mixed_modes_is_unknown():
    runs = [
        {"experiment_id": "EXP-1", "run_mode": "manual"},
        {"experiment_id": "EXP-1", "run_mode": "dry_run"},
    ]
    assert _source(runs).startswith("混合（来源未记录")
    assert _source([{"experiment_id": "EXP-1"}]) == "未知"


def test_other_experiment_runs_do_not_leak_into_source():
    runs = [
        {"experiment_id": "EXP-1", "execution_kind": "dry_run_simulation"},
        {"experiment_id": "EXP-2", "execution_kind": "real_target_execution"},
    ]
    assert _source(runs) == "演练模拟"


def test_verifier_label_marks_historical_placeholder():
    verifier_zh = _labels_ns()["verifier_zh"]
    assert verifier_zh("user") == "历史未知（旧数据）"
    assert verifier_zh("user-123") == "user-123"
    assert verifier_zh(None) == "未记录"
