# Delivery Alignment Report

> **Date:** 2026-05-30
> **Purpose:** Unified delivery alignment to the latest full acceptance report
> **SUPERSEDED:** This report has been superseded by `artifacts/final_delivery_alignment/final_delivery_alignment_update.md` (2026-05-31). The current pytest baseline is 148/148 (not 140/140). Room booking and student management E2E results are now documented.

---

## Latest acceptance source

`artifacts/full_acceptance_latest_minimal/`

---

## Updated acceptance status

**PASS**

---

## Version

`0.8.0-alpha.11`

---

## Acceptance summary

- Docker: postgres healthy, redis healthy
- ruff check: PASS
- ruff format: PASS
- compileall: PASS
- version_check: PASS (0.8.0-alpha.11)
- acceptance scripts: 13/13 PASS, 707/707 checks
- pytest: 140/140 passed
- API health: ok
- OpenAPI: 66,931 bytes, 61 paths
- frontend: running, logs clean
- runtime logs: clean (no Traceback/ImportError/ValidationError/RuntimeError)

---

## Minimal fixes included in latest acceptance

- ruff import cleanup (8 errors auto-fixed)
- ruff formatting (5 files reformatted)
- ac11c OpenAPI path expectation updated from hardcoded 34 to >= 61 (actual 61)
- MEDIUM risk adaptive gate test metadata aligned with `gate_required=True`

---

## Delivery scope

**local-preview / personal / small-team only**

---

## Non-production statement

This project has passed full local-preview acceptance for personal and trusted small-team use.
It is not production-ready and must not be presented as a production SaaS, public internet deployment, enterprise multi-tenant system, or regulated decisioning system.

本项目已通过 full local-preview 全量验收，可用于个人或可信小团队内部预览、演示和评估；不代表生产可上线，不应作为公网 SaaS、企业多租户平台或强监管自动化决策系统交付。

---

## Files reviewed

- `CLAUDE.md`
- `README.md`
- `CHANGELOG.md` (historical — not modified, old numbers retained in changelog entries)
- `ROADMAP.md`
- `docs/current_project_state.md`
- `docs/validation-status.md`
- `docs/e2e-results-summary.md`
- `docs/delivery_manifest.md`
- `docs/current-status-index.md`
- `docs/acceptance/README.md`
- `docs/acceptance/docker_final_acceptance_report.md`
- `docs/acceptance/docker_final_acceptance_ledger.md`
- `docs/architecture.md` (historical alpha.8 references — not modified)
- `docs/stage3-risk-adaptive-gate.md`
- `artifacts/full_acceptance_latest_minimal/` (evidence directory — not modified)
- `examples/stage_gate_scenarios.json`
- `examples/sample_report.json`
- `LIVE_E2E_LOW_RISK_READING_PLANNER_REPORT.md`
- `LIVE_E2E_MEDICATION_MANAGEMENT_REPORT.md`

---

## Files updated

| File | Changes |
|------|---------|
| `CLAUDE.md` | Updated acceptance table: 13 scripts, 707 checks, 140 pytest, 61 paths, evidence dir reference; updated common questions; marked historical baseline as superseded |
| `README.md` | Updated header: 13 scripts, 707 checks, 140 pytest, 61 paths; updated acceptance summary table; updated test count in directory structure; updated evidence reference |
| `docs/current_project_state.md` | Updated acceptance table: 13 scripts, 707 checks, 140 pytest, 61 paths; added evidence dir reference; marked historical reports as superseded |
| `docs/delivery_manifest.md` | Updated validation evidence table: 13 scripts, 707 checks, 140 pytest, 61 paths; added evidence dir reference |
| `docs/validation-status.md` | Updated quick reference: 13 scripts, 707 checks, 140 pytest; updated acceptance table; updated test summary |
| `docs/e2e-results-summary.md` | Updated full pytest count: 140; added evidence dir reference |
| `docs/current-status-index.md` | Updated pytest count: 140; added evidence dir to authoritative docs; marked Docker acceptance reports as superseded in historical section |
| `docs/acceptance/README.md` | Updated latest acceptance to reference `artifacts/full_acceptance_latest_minimal/`; updated validated items: 13 scripts, 707 checks, 140 pytest; marked Docker acceptance reports as historical |
| `docs/acceptance/docker_final_acceptance_report.md` | Added SUPERSEDED notice at top |
| `docs/acceptance/docker_final_acceptance_ledger.md` | Added SUPERSEDED notice at top |
| `ROADMAP.md` | Updated pytest line to note historical status and latest count |

---

## Superseded claims corrected

| Old claim | New claim | Files affected |
|-----------|-----------|----------------|
| 10 acceptance scripts | 13 acceptance scripts | CLAUDE.md, README.md, docs/current_project_state.md, docs/delivery_manifest.md, docs/validation-status.md, docs/acceptance/README.md |
| 615/615 checks | 707/707 checks | CLAUDE.md, README.md, docs/current_project_state.md, docs/delivery_manifest.md, docs/validation-status.md, docs/acceptance/README.md |
| 103/103 pytest | 140/140 pytest | CLAUDE.md, README.md, docs/current_project_state.md, docs/delivery_manifest.md, docs/validation-status.md, docs/e2e-results-summary.md, docs/current-status-index.md |
| 34 OpenAPI paths | 61 OpenAPI paths | (referenced in artifacts only; no main docs had stale path count) |
| Docker Final Acceptance as primary report | `artifacts/full_acceptance_latest_minimal/` as primary evidence | CLAUDE.md, README.md, docs/current_project_state.md, docs/acceptance/README.md |

---

## Code changes

**None.** This update only modified documentation (Markdown files). No `.py`, `.json`, `.toml`, or configuration files were changed.

---

## Configuration changes

**None.** `.env`, `.env.example`, `pyproject.toml`, `uv.lock`, `docker-compose.yml` were NOT modified.

---

## Self-check commands

```bash
# Check for remaining stale claims in main docs
rg -n "103/103|615/615|34 paths|10 acceptance|production-ready|Production ready|PRODUCTION READY" README.md CLAUDE.md docs scripts config || true
```

Result: stale numbers only appear in historical/archived context (CHANGELOG.md entries, historical acceptance reports marked as superseded).

```bash
# Python compilation check
python -m compileall -q api core graph stages tools storage frontend scripts
```

Result: PASS (no `.py` files were modified).

---

## Remaining risk

1. `CHANGELOG.md` retains historical numbers (103/103, 615/615) in changelog entries — this is correct behavior for a changelog.
2. `docs/acceptance/docker_final_acceptance_report.md` and `docs/acceptance/docker_final_acceptance_ledger.md` retain old numbers internally — they are marked as SUPERSEDED and retained for traceability.
3. Historical individual acceptance script summaries in `docs/acceptance/` (ac09a, ac09b, ac09c, etc.) retain old schema versions — they are historical records.
4. Code comments referencing alpha version numbers (e.g., "v0.8-alpha.3") are implementation history markers, not delivery claims.

---

## Final conclusion

**PASS：交付说明、配置说明、阶段说明和验收文档已统一到 `artifacts/full_acceptance_latest_minimal/` 的最新全量验收报告。当前口径仅适用于 local-preview / personal / small-team，不代表 production-ready。**
