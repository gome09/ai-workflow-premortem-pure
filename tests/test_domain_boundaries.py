# tests/test_domain_boundaries.py
"""Milestone 2: domain dependency direction and no new import cycles."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SERVICE_FILES = [
    "session_workflow.py",
    "governance.py",
    "evidence.py",
    "evaluation.py",
    "audit_trace.py",
    "access.py",
]
NEW_PACKAGE_DIRS = ["core/risk", "core/coverage", "core/governance", "core/services"]


def _module_level_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def _new_package_modules() -> list[Path]:
    paths: list[Path] = []
    for directory in NEW_PACKAGE_DIRS:
        paths.extend(sorted((ROOT / directory).glob("*.py")))
    return paths


def test_risk_and_coverage_do_not_depend_on_gates_or_services():
    for path in (ROOT / "core/risk").glob("*.py"):
        imports = _module_level_imports(path)
        assert not {name for name in imports if name.startswith("core.gates")}, path
        assert not {name for name in imports if name.startswith("core.coverage")}, path
        assert not {name for name in imports if name.startswith("core.services")}, path
        assert "core.session_service" not in imports, path

    for path in (ROOT / "core/coverage").glob("*.py"):
        imports = _module_level_imports(path)
        assert not {name for name in imports if name.startswith("core.gates")}, path
        assert not {name for name in imports if name.startswith("core.services")}, path
        assert "core.session_service" not in imports, path


def test_action_state_does_not_depend_on_services_or_facade():
    path = ROOT / "core/governance/action_state.py"
    imports = _module_level_imports(path)
    assert not {name for name in imports if name.startswith("core.services")}
    assert "core.session_service" not in imports
    assert "core.oversight_service" not in imports


def test_services_do_not_import_each_other_or_the_facade():
    for filename in SERVICE_FILES:
        path = ROOT / "core/services" / filename
        imports = _module_level_imports(path)
        service_imports = {
            name
            for name in imports
            if name.startswith("core.services.") and name != "core.services.access"
        }
        assert not service_imports, f"{filename} imports another domain service: {service_imports}"
        assert "core.session_service" not in imports, f"{filename} imports the facade"


def test_new_package_module_level_graph_is_acyclic():
    graph: dict[str, set[str]] = {}
    known: set[str] = set()
    for path in _new_package_modules():
        module = str(path.relative_to(ROOT).with_suffix("")).replace("\\", "/").replace("/", ".")
        known.add(module)
    for path in _new_package_modules():
        module = str(path.relative_to(ROOT).with_suffix("")).replace("\\", "/").replace("/", ".")
        graph[module] = {
            imported
            for imported in _module_level_imports(path)
            if imported in known and imported != module
        }

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        assert node not in visiting, f"new import cycle detected at {node}"
        if node in visited:
            return
        visiting.add(node)
        for neighbour in graph.get(node, set()):
            visit(neighbour)
        visiting.remove(node)
        visited.add(node)

    for module in graph:
        visit(module)


def test_domain_services_import_without_facade():
    import core.services.audit_trace  # noqa: F401
    import core.services.evaluation  # noqa: F401
    import core.services.evidence  # noqa: F401
    import core.services.governance  # noqa: F401
    import core.services.session_workflow  # noqa: F401

    assert True
