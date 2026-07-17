# Architecture

This project is an AI Workflow Pre-mortem & Human Oversight Tool, not a general workflow builder.

---

## 系统架构总览

```mermaid
graph TD
    FE["前端<br/>Streamlit Review Workbench"]
    API["API 层<br/>FastAPI + Nginx 反向代理"]
    Auth["认证授权<br/>JWT + RBAC + 多租户隔离"]
    Core["核心业务层<br/>Session / Stage / Gate Services"]
    Graph["工作流引擎<br/>LangGraph 状态机"]
    S1["Stage 1<br/>失败模式识别"]
    S2["Stage 2<br/>Human-in-the-Loop 设计"]
    S3["Stage 3<br/>Zero-Shot 压力测试"]
    S4["Stage 4<br/>触发策略生成"]
    Gate["门禁引擎<br/>Review Gate + Stage Gate"]
    LLM["LLM 适配层<br/>DeepSeek V4 Pro/Flash<br/>Mock LLM（演示模式）"]
    Search["搜索工具<br/>Tavily Search API"]
    DB["PostgreSQL<br/>会话持久化 + Alembic 迁移"]
    Cache["Redis<br/>限流计数器 + 状态缓存"]
    Monitor["可观测性<br/>Prometheus + Grafana"]

    FE -->|HTTPS / HTTP| API
    API --> Auth
    API --> Core
    Core --> Graph
    Graph --> S1 & S2 & S3 & S4
    S1 & S3 --> LLM
    S2 & S4 --> LLM
    S1 --> Search
    Graph --> Gate
    Core --> DB
    Core --> Cache
    API --> Monitor
```

---

## 四阶段工作流时序

```mermaid
sequenceDiagram
    participant U as 用户
    participant API as FastAPI
    participant Graph as LangGraph
    participant LLM as DeepSeek LLM
    participant Gate as 门禁引擎

    U->>API: POST /chat/{session_id}
    API->>Graph: execute_one_turn(ctx)
    Graph->>LLM: Stage 1 — 失败模式分析
    LLM-->>Graph: FailureMode[] + Evidence
    Graph->>Gate: 评估 Stage Gate
    alt Gate PASS
        Gate-->>Graph: advance → Stage 2
    else Gate BLOCK
        Gate-->>Graph: PendingHumanAction
        Graph-->>API: 返回阻断状态
        U->>API: POST /actions/{id}/resolve
        API->>Graph: 解除阻断，继续推进
    end
    Graph-->>API: stage result
    API-->>U: 200 OK + stage output
```

---

## Runtime Path

Current request execution flows through `SessionService` and the execution-mode coordinator before entering the graph runner:

```text
FastAPI / Streamlit
-> SessionService
-> core.execution_service.execute_one_turn(ctx)
   -> single_step
      -> graph.runner.run_one_step(ctx)
   -> langgraph_interrupt experimental mode
      -> graph.langgraph_interrupt_runner.invoke_one_turn_with_interrupts(ctx)
-> graph.nodes
-> StageExecutor
-> Review Gate
-> PendingHumanAction / SafetyFinding / EvidenceSource / EvalCase / EvalRun
-> PostgreSQL + Redis cache
```

`single_step` remains the default stable path. `langgraph_interrupt` is an experimental adapter path selected only through `WORKFLOW_EXECUTION_MODE=langgraph_interrupt`.

## Review and Action Resolution Path

Human review actions are resolved through service-layer coordination rather than by support modules advancing stages directly:

```text
FastAPI / Streamlit
-> SessionService (orchestration layer)
-> core.oversight_service.resolve_action(...)
   -> assert_action_resolution_allowed -> graph.transition_policy.evaluate_action_resolution(...)
-> SessionService.after_human_resolution -> stage_advancement_coordinator
   -> core.execution_service.sync_execution_after_action_resolution(...)
      -> single_step: no checkpoint mutation
      -> langgraph_interrupt: mark interrupt resumed/cancelled and consume resume once
-> stage gate re-evaluation
```

Note: `SessionService` is the orchestrator — `oversight_service.resolve_action` validates and resolves the action (delegating the policy check to `transition_policy`), then `SessionService` triggers execution synchronization via the stage advancement coordinator. The three modules run in the order shown, but are not chained inside `oversight_service`.

Stage rerun, revise, rollback, and sync-review-actions are explicit stage operations under `core.stage_operation_service` and `api.routers.stage`.

## Core Principles

- Workflow transitions are deterministic and code-controlled.
- LLMs generate analysis, not autonomous workflow transitions.
- High-risk decisions require human review.
- Evidence, safety findings, eval cases, eval runs, interrupt records, and report artifacts are first-class records.
- Graph, API, frontend, and reports consume the same stage readiness contract.
- Full runtime validation is intentionally separate from dependency-light contract tests.

## Key coordination points

（自 v1.0.0 确立，v1.3.0 复核仍然有效）

- `core/version.py` is the version source of truth.
- `core/stage_readiness_service.py` is the authoritative stage gate source.
- `graph/transition_policy.py` keeps backward-compatible transition and action-resolution helpers.
- `core/stage_resolution_service.py` maps blockers to concrete next operations.
- `core/stage_operation_service.py` performs explicit non-runtime stage operations.
- `core/execution_service.py` centralizes execution-mode dispatch and interrupt synchronization.
- `FailureMode.evidence_ids` preserves structured evidence references.
- User materials are represented as `EvidenceSource(source_type="user_material")`.
- Eval coverage and high-risk eval review are part of the Stage 3 gate.


## Doc/Test/Core Alignment Contract

Stage readiness, resolution, and advancement-decision contracts are enforced through the service layer (`core/stage_readiness_service.py`, `core/stage_resolution_service.py`, `core/stage_advancement_decision.py`) and validated by dedicated tests in `tests/`.

Runtime validation requires the full dependency/service environment: FastAPI startup, Streamlit startup, Docker compose, PostgreSQL, Redis, Tavily, real LLM calls, and end-to-end workflow replay.
