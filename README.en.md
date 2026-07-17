# AI Workflow Premortem

[![CI](https://github.com/gome09/ai-workflow-premortem-pure/actions/workflows/ci.yml/badge.svg)](https://github.com/gome09/ai-workflow-premortem-pure/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

English | [简体中文](README.md)

> Before an AI system ships, answer one question systematically: **where will it fail?**

## Why

In early 2026 alone, AI agents deleted production databases and moved millions of dollars without human approval. The common root cause was not model capability — it was that **foreseeable failure modes were never tested before deployment**. AI Workflow Premortem applies the software-engineering *pre-mortem* methodology to the inception phase of AI projects: assume the system has failed, then work backwards to find out how.

## What it does

A guided four-stage analysis pipeline with risk-adaptive gates and mandatory human oversight:

| Stage | Purpose |
|-------|---------|
| 1. Failure Mode Identification | Live web research + LLM reasoning to enumerate domain-specific failure modes |
| 2. Human-AI Workflow Design | Decide which decisions require human review; design oversight nodes |
| 3. Zero-Shot Stress Testing | Auto-generate EvalCases probing boundary behaviors |
| 4. Trigger Strategy | Deployment timing, trigger conditions, and monitoring strategy |

**Risk-adaptive stage gates** (LOW / MEDIUM / HIGH / CRITICAL) tighten pass conditions as project risk rises — a CRITICAL-tier project (e.g. medical diagnosis) cannot pass Stage 3 without red-team tests, regression evals, and explicit expert approval. Blocking a high-risk project is **by design, not a defect**.

**Architecture principle:** workflow state transitions are deterministic and code-controlled. The LLM generates analysis content; it never decides flow transitions. Evidence, safety findings, eval runs, human interventions, and audit events are first-class records.

## Quick start (offline demo, no API key)

```bash
uv sync --all-extras
make demo-api   # backend on :8000 (auto-provisions .env from .env.demo: mock LLM + SQLite)
make demo-ui    # Streamlit frontend on :8501
```

Or zero-dependency: open `ai_workflow_premortem_demo.html` directly in a browser.

## Tech stack

FastAPI · LangGraph · Streamlit · PostgreSQL/SQLite · Redis · JWT/RBAC · Docker Compose · Prometheus/Grafana

## Compliance mapping

The risk taxonomy engine maps findings to NIST AI RMF / NIST AI 600-1, OWASP LLM Top 10 (2025) & Agentic Top 10 (ASI, 2026), TC260 agent-deployment guidance, and ISO/IEC 42001 clauses. See [docs/](docs/README.md) (Chinese).

## Documentation

Full documentation (architecture, API reference, security model, compliance mappings) is currently in Chinese under [docs/](docs/README.md). The codebase uses English identifiers throughout; issues and PRs in English are welcome.

## License

Apache-2.0
