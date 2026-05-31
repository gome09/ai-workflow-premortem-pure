#!/usr/bin/env python3
"""Static source-freeze audit for v0.8.0-alpha.11.

This script performs source-only checks. It does not start services, connect
to databases, call LLM/Search providers, import application modules, or run
pytest. It is intended for the later manual source-freeze acceptance pass.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def literal_from_assign(tree: ast.Module, name: str) -> Any:
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name:
                return ast.literal_eval(node.value)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise KeyError(name)


def extract_contract() -> dict[str, Any]:
    tree = ast.parse(read("core/stage_advancement_contract.py"))
    return {
        "BLOCKER_TYPES": tuple(literal_from_assign(tree, "BLOCKER_TYPES")),
        "REQUIRED_RESOLUTIONS": tuple(literal_from_assign(tree, "REQUIRED_RESOLUTIONS")),
        "STAGE_ADVANCEMENT_CONTRACT": literal_from_assign(tree, "STAGE_ADVANCEMENT_CONTRACT"),
        "RESOLUTION_OPERATION_CONTRACT": literal_from_assign(tree, "RESOLUTION_OPERATION_CONTRACT"),
    }


def strings_in_gate_rules() -> dict[str, set[str]]:
    blocker_types: set[str] = set()
    required_resolutions: set[str] = set()
    for path in (ROOT / "core" / "gates" / "rules").glob("*.py"):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        blocker_types.update(re.findall(r"blocker_type\s*=\s*[\"']([a-zA-Z0-9_]+)[\"']", text))
        required_resolutions.update(
            re.findall(r"required_resolution\s*=\s*[\"']([a-zA-Z0-9_]+)[\"']", text)
        )
    return {"blocker_types": blocker_types, "required_resolutions": required_resolutions}


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    contract = extract_contract()

    blocker_types = set(contract["BLOCKER_TYPES"])
    contract_keys = set(contract["STAGE_ADVANCEMENT_CONTRACT"].keys())
    if blocker_types != contract_keys:
        errors.append(
            "BLOCKER_TYPES and STAGE_ADVANCEMENT_CONTRACT keys differ: "
            f"missing_in_contract={sorted(blocker_types - contract_keys)}, "
            f"extra_in_contract={sorted(contract_keys - blocker_types)}"
        )

    required = set(contract["REQUIRED_RESOLUTIONS"])
    operation_keys = set(contract["RESOLUTION_OPERATION_CONTRACT"].keys())
    missing_operation = sorted(required - operation_keys)
    if missing_operation:
        errors.append(f"Missing RESOLUTION_OPERATION_CONTRACT entries: {missing_operation}")

    unknown_contract_resolutions = sorted(
        str(meta.get("required_resolution"))
        for meta in contract["STAGE_ADVANCEMENT_CONTRACT"].values()
        if str(meta.get("required_resolution")) not in required
    )
    if unknown_contract_resolutions:
        errors.append(
            f"Unknown contract required_resolution values: {unknown_contract_resolutions}"
        )

    emitted = strings_in_gate_rules()
    unknown_emitted_blockers = sorted(emitted["blocker_types"] - blocker_types)
    unknown_emitted_resolutions = sorted(emitted["required_resolutions"] - required)
    if unknown_emitted_blockers:
        errors.append(f"Gate rules emit unknown blocker_type values: {unknown_emitted_blockers}")
    if unknown_emitted_resolutions:
        errors.append(
            f"Gate rules emit unknown required_resolution values: {unknown_emitted_resolutions}"
        )

    version_text = read("core/version.py")
    if 'APP_VERSION = "0.8.0-alpha.11"' not in version_text:
        errors.append("core/version.py does not report APP_VERSION 0.8.0-alpha.11")
    if 'PACKAGE_STAGE = "v0.8.0-alpha.11-freeze-fix"' not in version_text:
        errors.append("core/version.py does not report alpha.11 freeze-fix package stage")
    if 'RUNTIME_VALIDATION = "deferred_by_instruction"' not in version_text:
        errors.append("core/version.py runtime validation is not deferred_by_instruction")

    roadmap_text = read("ROADMAP.md")
    if "Current package status: `v0.8.0-alpha.9" in roadmap_text:
        errors.append("ROADMAP.md still marks the active package as alpha.9")

    policy_text = read("core/eval_regression_policy.py")
    if '"policy_version": "v0.8.0-alpha.9"' in policy_text:
        errors.append("Eval regression policy still hard-codes alpha.9 policy_version")
    if "from core.version import APP_VERSION" not in policy_text:
        warnings.append("Eval regression policy does not visibly import APP_VERSION")

    api_audit = read("docs/stage_advancement_api_return_audit_alpha11.md")
    required_api_rows = [
        "create_eval_dataset_from_stage3",
        "add_eval_dataset_cases",
        "remove_eval_dataset_cases",
        "set_eval_dataset_baseline",
    ]
    for row in required_api_rows:
        if row not in api_audit:
            errors.append(f"alpha.11 API audit is missing EvalDataset row: {row}")

    result = {
        "package_stage": "v0.8.0-alpha.11-freeze-fix",
        "runtime_validation": "deferred_by_instruction",
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "blocker_types": len(blocker_types),
            "required_resolutions": len(required),
            "resolution_operations": len(operation_keys),
            "gate_rule_blocker_literals": sorted(emitted["blocker_types"]),
            "gate_rule_required_resolution_literals": sorted(emitted["required_resolutions"]),
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
