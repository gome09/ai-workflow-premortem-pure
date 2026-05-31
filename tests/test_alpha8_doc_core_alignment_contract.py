# tests/test_alpha8_doc_core_alignment_contract.py
"""Dependency-light doc/test/core alignment checks for v0.8.0-alpha.9.

These tests intentionally parse source files instead of importing API, storage,
LLM, Tavily, Redis, PostgreSQL, or Streamlit dependencies. They are designed to
catch stale Markdown/test acceptance claims while leaving core code untouched.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALIGNMENT_DOC = PROJECT_ROOT / "docs" / "v0_6_0_alpha_8_core_code_alignment_contract.md"
ACCEPTANCE_DOC = PROJECT_ROOT / "tests" / "ACCEPTANCE_TEST_ALIGNMENT_ALPHA8.md"


def _read(relative: str | Path) -> str:
    path = PROJECT_ROOT / relative if isinstance(relative, str) else relative
    return path.read_text(encoding="utf-8")


def _literal_from_module(relative: str, name: str) -> Any:
    tree = ast.parse(_read(relative))
    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
        ):
            return ast.literal_eval(node.value)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in {relative}")


def _markdown_table_after_heading(markdown: str, heading: str) -> list[dict[str, str]]:
    marker = f"## {heading}"
    assert marker in markdown, f"Missing heading: {marker}"
    section = markdown.split(marker, 1)[1]
    next_heading = re.search(r"\n##\s+", section)
    if next_heading:
        section = section[: next_heading.start()]
    lines = [line.strip() for line in section.splitlines() if line.strip().startswith("|")]
    assert len(lines) >= 2, f"No Markdown table found after heading: {heading}"
    header = [cell.strip().strip("`") for cell in lines[0].strip("|").split("|")]
    rows: list[dict[str, str]] = []
    for line in lines[2:]:
        cells = [cell.strip().strip("`") for cell in line.strip("|").split("|")]
        if len(cells) != len(header):
            continue
        rows.append(dict(zip(header, cells)))
    return rows


def _router_paths_from_source(relative: str) -> set[tuple[str, str]]:
    tree = ast.parse(_read(relative))
    paths: set[tuple[str, str]] = set()
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            if not isinstance(func, ast.Attribute):
                continue
            method = func.attr.upper()
            if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                continue
            if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
                continue
            paths.add((method, "/sessions" + str(decorator.args[0].value)))
    return paths


def test_alignment_doc_blocker_matrix_matches_core_contract() -> None:
    doc = _read(ALIGNMENT_DOC)
    contract = _literal_from_module(
        "core/stage_advancement_contract.py", "STAGE_ADVANCEMENT_CONTRACT"
    )
    rows = _markdown_table_after_heading(doc, "Authoritative blocker to resolution matrix")
    by_blocker = {row["Blocker type"]: row for row in rows}

    assert set(contract) == set(by_blocker)
    for blocker_type, item in contract.items():
        row = by_blocker[blocker_type]
        assert row["Required resolution"] == item["required_resolution"]
        assert (
            row["Approval override allowed"]
            == str(item.get("approval_override_allowed", False)).lower()
        )
        assert row["Core source"] == "core/stage_advancement_contract.py"


def test_alignment_doc_resolution_operation_matrix_matches_core_contract() -> None:
    doc = _read(ALIGNMENT_DOC)
    contract = _literal_from_module(
        "core/stage_advancement_contract.py", "RESOLUTION_OPERATION_CONTRACT"
    )
    rows = _markdown_table_after_heading(doc, "Authoritative resolution operation matrix")
    by_resolution = {row["Required resolution"]: row for row in rows}

    assert set(contract) == set(by_resolution)
    for resolution, item in contract.items():
        row = by_resolution[resolution]
        assert row["API-capable contract"] == str(item.get("can_execute_via_api", False)).lower()
        assert row["API method"] == str(item.get("api_method") or "")
        assert row["API path template"] == str(item.get("api_path_template") or "")


def test_alignment_doc_stage_api_surface_matches_router_decorators() -> None:
    doc = _read(ALIGNMENT_DOC)
    rows = _markdown_table_after_heading(doc, "Authoritative stage API surface")
    doc_paths = {(row["Method"], row["Path"]) for row in rows}
    source_paths = _router_paths_from_source("api/routers/stage.py")
    assert doc_paths == source_paths


def test_alignment_docs_describe_read_only_gate_and_deferred_runtime_boundary() -> None:
    alignment = _read(ALIGNMENT_DOC)
    acceptance = _read(ACCEPTANCE_DOC)
    combined = alignment + "\n" + acceptance

    required_phrases = [
        "evaluate_stage_gate",
        "read-only gate",
        "Dependency-light",
        "Full runtime validation remains deferred",
        "must not be used as proof of full alpha.8 behavior",
        "does not modify core workflow logic",
    ]
    for phrase in required_phrases:
        assert phrase in combined

    prohibited_claims = [
        "full pytest passed",
        "API startup passed",
        "Streamlit startup passed",
        "Docker compose passed",
        "PostgreSQL integration passed",
        "Redis integration passed",
        "real LLM replay passed",
        "end-to-end workflow validation passed",
    ]
    # The alignment doc may list prohibited wording as examples, but it must not
    # claim them outside the explicit "Do not replace it with" warning block.
    warning_block = alignment.split("Do not replace it with", 1)[-1]
    for claim in prohibited_claims:
        assert claim in warning_block


def test_acceptance_notes_require_source_truth_instead_of_hard_coded_doc_lists() -> None:
    acceptance = _read(ACCEPTANCE_DOC)
    assert "source-of-truth files" in acceptance
    assert "hard-coded expected list" in acceptance
    assert "calling private node/helper functions by hand" in acceptance
    assert "core.execution_service.execute_one_turn(ctx)" in acceptance
    assert "graph.runner.run_one_step(ctx)" in acceptance
