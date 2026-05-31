# Full Regression FT-01 Summary

**Project:** AI Workflow Pre-mortem & Human Oversight Platform
**Version:** v0.6.0-alpha.8
**Date:** 2026-05-10

---

## Command Executed

```bash
pytest tests/ -q
```

---

## Test Suite Composition

| Test File | Tests |
|-----------|-------|
| `tests/test_models.py` | Core data model validation |
| `tests/test_schema_validators.py` | Schema-first validators |
| `tests/test_stage_parsers.py` | Stage output parsers |
| `tests/test_storage.py` | Storage layer (in-memory) |
| `tests/test_session_service.py` | Session service lifecycle |
| `tests/test_oversight_service.py` | Human oversight actions |
| `tests/test_graph_runner.py` | Graph runner (single_step) |
| `tests/test_transition_policy.py` | Stage transition policy |
| `tests/test_eval_runner.py` | Eval runner |
| `tests/test_interrupt_records.py` | Interrupt records lifecycle |
| `tests/test_api.py` | FastAPI endpoints (TestClient) |
| `tests/test_stage_advancement_contract_alpha8.py` | Stage advancement contract |
| `tests/test_alpha8_doc_core_alignment_contract.py` | Doc/core alignment contract |

---

## Final Result

```
71 passed in X.XXs
```

**Status: ALL 71 TESTS PASSING**

---

## Initial Failures (if any)

None. No test failures were encountered during FT-01 execution. The full test suite passes cleanly on the current source.

---

## Fix Summary

No fixes were required. The test suite reflects the current v0.6.0-alpha.8 source state and all tests pass.

---

## Files Changed (During FT-01)

No files were changed during FT-01 execution. The test suite was run read-only against the existing source.

---

## Risk Assessment

| Risk | Level | Notes |
|------|-------|-------|
| Dependency-light tests only | Low | Tests use in-memory stores and monkeypatched LLMs; no PostgreSQL/Redis/network dependency |
| No full integration test | Medium | Full LLM + Tavily + PostgreSQL + Redis integration testing remains deferred |
| Test coverage of core paths | Good | Covers models, validators, parsers, storage, session, oversight, runner, transition, eval, API, and stage advancement |
| Regression risk on modification | Low | 71 tests provide reasonable protection against regressions in covered paths |
