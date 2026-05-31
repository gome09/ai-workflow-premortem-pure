# Delivery Alignment Update — 2026-05-30

## 1. Update objective

Unify all project documentation, configuration descriptions, stage files, acceptance documents, and delivery documents to the latest full acceptance report in `artifacts/full_acceptance_latest_minimal/`.

## 2. Latest acceptance source

`artifacts/full_acceptance_latest_minimal/full_acceptance_summary.md`

## 3. Modified files

| File | Change type |
|------|-------------|
| `CLAUDE.md` | Updated acceptance numbers, evidence dir reference, common questions |
| `README.md` | Updated header, acceptance summary, test count, evidence reference |
| `docs/current_project_state.md` | Updated acceptance table, evidence dir, historical markers |
| `docs/delivery_manifest.md` | Updated validation evidence table, evidence dir |
| `docs/validation-status.md` | Updated quick reference, acceptance table, test summary |
| `docs/e2e-results-summary.md` | Updated pytest count, evidence reference |
| `docs/current-status-index.md` | Updated pytest count, evidence dir, historical markers |
| `docs/acceptance/README.md` | Updated latest acceptance reference, validated items, historical section |
| `docs/acceptance/docker_final_acceptance_report.md` | Added SUPERSEDED notice |
| `docs/acceptance/docker_final_acceptance_ledger.md` | Added SUPERSEDED notice |
| `ROADMAP.md` | Updated pytest line with historical annotation |
| `docs/delivery_alignment_report.md` | NEW — delivery alignment report |

## 4. Unified key numbers

| Metric | Value |
|--------|-------|
| Version | `0.8.0-alpha.11` |
| Acceptance scripts | 13/13 PASS |
| Acceptance checks | 707/707 |
| Pytest passed | 148/148 |
| OpenAPI paths | 61 |
| OpenAPI bytes | 66,931 |

## 5. Cleaned or marked-as-historical old claims

| Old claim | Status |
|-----------|--------|
| 10 acceptance scripts | Corrected to 13 in all main delivery docs |
| 615/615 checks | Corrected to 707/707 in all main delivery docs |
| 103/103 pytest | Corrected to 148/148 in all main delivery docs; 103/103 retained in historical sections with annotations |
| 34 OpenAPI paths | Not present in main delivery docs (only in artifacts error log) |
| Docker Final Acceptance as primary report | Superseded by `artifacts/full_acceptance_latest_minimal/`; historical reports marked SUPERSEDED |

## 6. Code changes

**None.** Only Markdown documentation files were modified.

## 7. Configuration changes

**None.** `.env`, `pyproject.toml`, `uv.lock`, `docker-compose.yml` were NOT modified.

## 8. Self-check results

```bash
rg -n "103/103|615/615|34 paths|10 acceptance" README.md CLAUDE.md docs/current_project_state.md docs/validation-status.md docs/delivery_manifest.md docs/current-status-index.md docs/acceptance/README.md ROADMAP.md docs/e2e-results-summary.md
```

Result: Only in historical/annotated context:
- `CLAUDE.md:43` — Historical Baseline section (marked superseded)
- `ROADMAP.md:26` — annotated with "historical; latest: 148/148 PASS"

```bash
python -m compileall -q api core graph stages tools storage frontend scripts
```

Result: PASS (no output = no errors)

## 9. Remaining risk

1. `CHANGELOG.md` retains historical numbers in changelog entries — correct behavior.
2. `docs/acceptance/docker_final_acceptance_report.md` retains old numbers internally — marked SUPERSEDED.
3. Historical individual acceptance script summaries retain old schema versions — historical records.
4. Code comments referencing alpha version numbers are implementation history markers.

## 10. Final conclusion

**PASS：交付说明、配置说明、阶段说明和验收文档已统一到 `artifacts/full_acceptance_latest_minimal/` 的最新全量验收报告。当前口径仅适用于 local-preview / personal / small-team，不代表 production-ready。**
