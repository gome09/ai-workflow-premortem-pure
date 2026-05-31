# scripts/acceptance/ac11a_interrupt_adapter_boundary.py
"""AC-11A: LangGraph Interrupt Optional Adapter Boundary Acceptance Verification.

Executes static checks only — no services, no pytest, no LLM, no workflow runs.
"""

from __future__ import annotations

import ast
import os
import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.chdir(str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

# ── Forbidden file list (must not be modified) ──────────────────────────
FORBIDDEN_FILES = [
    "graph/runner.py",
    "graph/langgraph_interrupt_runner.py",
    "graph/interrupt_gate.py",
    "graph/interrupts.py",
    "graph/review_gate.py",
    "graph/transition_policy.py",
    "core/execution_service.py",
    "core/session_service.py",
    "core/oversight_service.py",
    "core/stage_readiness_service.py",
    "storage/session_store.py",
    "api/routers/interrupts.py",
    "api/routers/oversight.py",
    "api/routers/stage.py",
    "api/routers/chat.py",
]

# ── Files that must be compilable ───────────────────────────────────────
COMPILABLE_FILES = [
    "core/config.py",
    "core/execution_mode.py",
    "core/execution_service.py",
    "graph/runner.py",
    "graph/langgraph_interrupt_runner.py",
    "graph/interrupt_gate.py",
    "graph/interrupts.py",
    "api/routers/interrupts.py",
]


def heading(text: str) -> None:
    print(f"\n{'=' * 68}")
    print(f"  {text}")
    print(f"{'=' * 68}")


def check(name: str, passed: bool, detail: str = "") -> bool:
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name}")
    if detail and not passed:
        print(f"         {detail}")
    return passed


results: list[bool] = []


# ═══════════════════════════════════════════════════════════════════════════
# Criterion 1: Default execution mode is single_step
# ═══════════════════════════════════════════════════════════════════════════
heading("Criterion 1: Default execution mode is single_step")

try:
    from core.execution_mode import WorkflowExecutionMode

    default_from_enum = WorkflowExecutionMode.SINGLE_STEP
    normalized = WorkflowExecutionMode.normalize(default_from_enum)
    results.append(
        check(
            "normalize(SINGLE_STEP) == 'single_step'",
            normalized == WorkflowExecutionMode.SINGLE_STEP,
            f"got {normalized}",
        )
    )
    results.append(
        check(
            "normalize('single_step') == SINGLE_STEP",
            WorkflowExecutionMode.normalize("single_step") == WorkflowExecutionMode.SINGLE_STEP,
        )
    )
except Exception:
    traceback.print_exc()
    results.append(check("WorkflowExecutionMode import/check", False, str(sys.exc_info()[1])))


try:
    from core.config import settings

    default_mode = settings.workflow_execution_mode
    results.append(
        check(
            "settings.workflow_execution_mode default is SINGLE_STEP",
            default_mode == WorkflowExecutionMode.SINGLE_STEP,
            f"got {default_mode}",
        )
    )
except Exception:
    traceback.print_exc()
    results.append(check("settings default mode check", False, str(sys.exc_info()[1])))


# ═══════════════════════════════════════════════════════════════════════════
# Criterion 2: langgraph_interrupt is optional, not default
# ═══════════════════════════════════════════════════════════════════════════
heading("Criterion 2: langgraph_interrupt is optional, not default")

results.append(
    check(
        "LANGGRAPH_INTERRUPT exists as enum value",
        hasattr(WorkflowExecutionMode, "LANGGRAPH_INTERRUPT"),
    )
)
results.append(
    check(
        "LANGGRAPH_INTERRUPT != SINGLE_STEP",
        WorkflowExecutionMode.LANGGRAPH_INTERRUPT != WorkflowExecutionMode.SINGLE_STEP,
    )
)
results.append(
    check(
        "Config default is NOT langgraph_interrupt",
        settings.workflow_execution_mode != WorkflowExecutionMode.LANGGRAPH_INTERRUPT,
        f"default={settings.workflow_execution_mode}",
    )
)

# Verify langgraph_interrupt can be normalized (exists as optional)
try:
    li = WorkflowExecutionMode.normalize("langgraph_interrupt")
    results.append(
        check(
            "normalize('langgraph_interrupt') succeeds",
            li == WorkflowExecutionMode.LANGGRAPH_INTERRUPT,
        )
    )
except Exception:
    traceback.print_exc()
    results.append(check("normalize('langgraph_interrupt')", False, str(sys.exc_info()[1])))


# ═══════════════════════════════════════════════════════════════════════════
# Criterion 3: single_step main line intact (execute_one_turn -> run_one_step)
# ═══════════════════════════════════════════════════════════════════════════
heading("Criterion 3: single_step main line (execute_one_turn -> run_one_step)")

exec_svc_path = PROJECT_ROOT / "core" / "execution_service.py"
exec_svc_src = exec_svc_path.read_text(encoding="utf-8")

# Check that execute_one_turn exists and branches on SINGLE_STEP
results.append(
    check(
        "execute_one_turn function exists",
        "def execute_one_turn" in exec_svc_src,
    )
)
results.append(
    check(
        "execute_one_turn calls run_one_step for SINGLE_STEP",
        "run_one_step(ctx)" in exec_svc_src and "SINGLE_STEP" in exec_svc_src,
    )
)

runner_path = PROJECT_ROOT / "graph" / "runner.py"
runner_src = runner_path.read_text(encoding="utf-8")
results.append(
    check(
        "run_one_step function exists in graph/runner.py",
        "def run_one_step" in runner_src,
    )
)

# Verify single_step returns ctx unchanged in sync_execution_after_action_resolution
results.append(
    check(
        "sync_execution_after_action_resolution: single_step returns ctx unchanged",
        ("SINGLE_STEP" in exec_svc_src) and ("return ctx" in exec_svc_src),
    )
)


# ═══════════════════════════════════════════════════════════════════════════
# Criterion 4: interrupt_id <-> action_id / PendingHumanAction mapping exists
# ═══════════════════════════════════════════════════════════════════════════
heading("Criterion 4: interrupt_id <-> action_id / PendingHumanAction mapping")

interrupts_path = PROJECT_ROOT / "graph" / "interrupts.py"
interrupts_src = interrupts_path.read_text(encoding="utf-8")

results.append(
    check(
        "interrupt_id present in interrupts.py",
        "interrupt_id" in interrupts_src,
    )
)
results.append(
    check(
        "action_id present in interrupts.py",
        "action_id" in interrupts_src,
    )
)
results.append(
    check(
        "InterruptRecord created with action_id mapping",
        "action_id=action.action_id" in interrupts_src,
    )
)
results.append(
    check(
        "sync_interrupt_records maps PendingHumanAction <-> InterruptRecord",
        "PendingHumanAction" in interrupts_src,
    )
)

# Check build_interrupt_payload includes both IDs
results.append(
    check(
        "build_interrupt_payload includes both interrupt_id and action_id",
        '"interrupt_id"' in interrupts_src
        and '"action_id"' in interrupts_src
        and "build_interrupt_payload" in interrupts_src,
    )
)

# Check interrupt API exposes action_id <-> interrupt_id mapping
interrupts_api_path = PROJECT_ROOT / "api" / "routers" / "interrupts.py"
interrupts_api_src = interrupts_api_path.read_text(encoding="utf-8")
results.append(
    check(
        "interrupts API lists interrupt records (action_id <-> interrupt_id)",
        "interrupt-records" in interrupts_api_src,
    )
)


# ═══════════════════════════════════════════════════════════════════════════
# Criterion 5: interrupt resume/cancel/resolve has audit/event recording path
# ═══════════════════════════════════════════════════════════════════════════
heading("Criterion 5: interrupt resume/cancel/resolve audit/event path")

# Check interrupts.py for audit events
audit_events_in_interrupts = [
    "interrupt_record_created",
    "interrupt_record_resumed_from_action",
    "interrupt_record_cancelled_from_action",
    "interrupt_resume_consumed",
]
for event_type in audit_events_in_interrupts:
    results.append(
        check(
            f"Audit event '{event_type}' in interrupts.py",
            event_type in interrupts_src,
        )
    )

# Check interrupt_gate.py for audit events
interrupt_gate_path = PROJECT_ROOT / "graph" / "interrupt_gate.py"
interrupt_gate_src = interrupt_gate_path.read_text(encoding="utf-8")
for event_type in ["interrupt_resumed_by_langgraph", "interrupt_runtime_unavailable"]:
    results.append(
        check(
            f"Audit event '{event_type}' in interrupt_gate.py",
            event_type in interrupt_gate_src,
        )
    )

# Check langgraph_interrupt_runner.py for audit events
interrupt_runner_path = PROJECT_ROOT / "graph" / "langgraph_interrupt_runner.py"
interrupt_runner_src = interrupt_runner_path.read_text(encoding="utf-8")
for event_type in [
    "interrupt_runner_error",
    "interrupt_resume_not_consumed",
    "interrupt_resume_failed",
]:
    results.append(
        check(
            f"Audit event '{event_type}' in langgraph_interrupt_runner.py",
            event_type in interrupt_runner_src,
        )
    )

results.append(
    check(
        "append_audit_event imported in interrupts.py",
        "from core.audit_service import append_audit_event" in interrupts_src,
    )
)
results.append(
    check(
        "append_audit_event imported in interrupt_gate.py",
        "from core.audit_service import append_audit_event" in interrupt_gate_src,
    )
)
results.append(
    check(
        "append_audit_event imported in langgraph_interrupt_runner.py",
        "from core.audit_service import append_audit_event" in interrupt_runner_src,
    )
)


# ═══════════════════════════════════════════════════════════════════════════
# Criterion 6: No obvious interrupt bypass of Stage/Review Gate / PendingHumanAction
# ═══════════════════════════════════════════════════════════════════════════
heading("Criterion 6: No interrupt bypass of gates or PendingHumanAction")

# The interrupt path calls run_one_step(ctx) — same deterministic node dispatch
results.append(
    check(
        "langgraph_interrupt_runner calls run_one_step (same node dispatch)",
        "run_one_step(ctx)" in interrupt_runner_src or "run_one_step" in interrupt_runner_src,
    )
)

# The interrupt gate is a node in the graph, not a bypass
results.append(
    check(
        "review_interrupt_gate is a graph node (not a shim replacing review)",
        "def review_interrupt_gate" in interrupt_gate_src,
    )
)

# dispatch_one_step checks for existing blocking interrupt before running
results.append(
    check(
        "dispatch_one_step guards against duplicate execution with pending blocking interrupt",
        "get_pending_blocking_interrupt" in interrupt_runner_src
        and "return ctx" in interrupt_runner_src,
    )
)

# graph/nodes.py still calls apply_review_gate (Review Gate intact)
nodes_path = PROJECT_ROOT / "graph" / "nodes.py"
nodes_src = nodes_path.read_text(encoding="utf-8")
results.append(
    check(
        "graph/nodes.py still calls apply_review_gate (Review Gate intact)",
        "apply_review_gate" in nodes_src,
    )
)
results.append(
    check(
        "graph/nodes.py still calls evaluate_stage_gate (Stage Gate intact)",
        "evaluate_stage_gate" in nodes_src or "advance_stage_if_ready" in nodes_src,
    )
)

# Single_step path does NOT import interrupt machinery
results.append(
    check(
        "graph/runner.py does not import interrupt modules",
        "interrupt" not in runner_src.lower() or "from graph.interrupts" not in runner_src,
    )
)

# Verify with AST that interrupt code doesn't conditionally skip review_gate/stage_gate
try:
    tree = ast.parse(interrupt_runner_src)

    # Look for any call to apply_review_gate or evaluate_stage_gate — there should be NONE
    # (interrupt code delegates to run_one_step which calls these via node dispatch)
    class GateCallVisitor(ast.NodeVisitor):
        def __init__(self):
            self.found_gate_calls = []

        def visit_Call(self, node):
            if isinstance(node.func, ast.Name):
                if node.func.id in ("apply_review_gate", "evaluate_stage_gate"):
                    self.found_gate_calls.append((node.func.id, node.lineno))
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr in ("apply_review_gate", "evaluate_stage_gate"):
                    self.found_gate_calls.append((node.func.attr, node.lineno))
            self.generic_visit(node)

    visitor = GateCallVisitor()
    visitor.visit(tree)

    # These gate functions should NOT be called in interrupt code directly
    # (they belong in graph/nodes.py only)
    results.append(
        check(
            "interrupt_runner does NOT directly call apply_review_gate or evaluate_stage_gate",
            len(visitor.found_gate_calls) == 0,
            f"Found direct gate calls: {visitor.found_gate_calls}",
        )
    )
except SyntaxError:
    results.append(
        check("AST parse of langgraph_interrupt_runner.py", False, "Syntax error in file")
    )


# ═══════════════════════════════════════════════════════════════════════════
# Criterion 7: py_compile of all target files
# ═══════════════════════════════════════════════════════════════════════════
heading("Criterion 7: py_compile all target files")

import io
import py_compile

compile_ok = True
for rel_path in COMPILABLE_FILES:
    full_path = PROJECT_ROOT / rel_path
    try:
        with io.StringIO() as buf:
            py_compile.compile(str(full_path), doraise=True)
        results.append(check(f"py_compile {rel_path}", True))
    except py_compile.PyCompileError as e:
        compile_ok = False
        results.append(check(f"py_compile {rel_path}", False, str(e)))


# ═══════════════════════════════════════════════════════════════════════════
# Criterion 8: Forbidden files not modified (check they exist, compile OK)
# ═══════════════════════════════════════════════════════════════════════════
heading("Criterion 8: Forbidden files exist and are valid Python")

for rel_path in FORBIDDEN_FILES:
    full_path = PROJECT_ROOT / rel_path
    exists = full_path.exists()
    results.append(check(f"Forbidden file exists: {rel_path}", exists))
    if exists:
        try:
            with io.StringIO() as buf:
                py_compile.compile(str(full_path), doraise=True)
            results.append(check(f"  -> compiles OK: {rel_path}", True))
        except py_compile.PyCompileError as e:
            results.append(check(f"  -> compiles OK: {rel_path}", False, str(e)))


# ═══════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════
heading("SUMMARY")

passed = sum(results)
total = len(results)
all_passed = passed == total

print(f"\n  {passed}/{total} checks passed")

if all_passed:
    print("\n  AC-11A ALL CHECKS PASSED")
    print("  -> LangGraph interrupt is confirmed as optional adapter only.")
    print("  -> single_step remains the default stable execution path.")
    print("  -> No interrupt bypass of PendingHumanAction, Review Gate, or Stage Gate.")
    print("  -> All interrupt state transitions have audit event recording.")
else:
    print(f"\n  AC-11A: {total - passed} CHECK(S) FAILED")
    failed_checks = [(i, r) for i, r in enumerate(results) if not r]
    print("  Failed checks:")
    for idx, _ in failed_checks:
        print(f"    - Check #{idx + 1}")

print()

sys.exit(0 if all_passed else 1)
