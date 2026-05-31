# Stage Advancement API Return Audit — alpha.11 freeze-fix

Generated: 2026-05-29  
Package stage: `v0.8.0-alpha.11-freeze-fix`  
Runtime validation: `deferred_by_instruction`

This document corrects the alpha.10 source-level API audit drift. It is a static source audit and does not call API endpoints.

## Audit rule

Gate-affecting mutating endpoints should return or contain:

```text
operation
result
stage_id
stage_advancement_decision
next_required_operation
runtime_validation
metadata
```

Read-only endpoints may return domain payloads, but must not invent separate stage-advancement semantics.

## Corrected alpha.11 finding

The following EvalDataset endpoints are gate-affecting because they can change the Stage 3 Eval Regression gate state:

| Router File | Method | Path | Function | Gate-affecting | Expected Return | Source-level Note |
|---|---|---|---|---:|---|---|
| `api/routers/eval_datasets.py` | `POST` | `/{session_id}/eval-datasets` | `create_eval_dataset` | yes | StageOperationEnvelope or decision-bearing payload | Creates a gate-relevant dataset when tags/source/scenario mark it as gate-required. |
| `api/routers/eval_datasets.py` | `POST` | `/{session_id}/eval-datasets/from-stage3` | `create_eval_dataset_from_stage3` | yes | StageOperationEnvelope or decision-bearing payload | Creates a dataset from Stage 3 EvalCase records; can resolve `dataset_empty` setup gaps. |
| `api/routers/eval_datasets.py` | `POST` | `/{session_id}/eval-datasets/{dataset_id}/cases` | `add_eval_dataset_cases` | yes | StageOperationEnvelope or decision-bearing payload | Adds EvalCase ids and can unblock `dataset_empty`. |
| `api/routers/eval_datasets.py` | `DELETE` | `/{session_id}/eval-datasets/{dataset_id}/cases` | `remove_eval_dataset_cases` | yes | StageOperationEnvelope or decision-bearing payload | Changes dataset case hash and can make experiments stale. |
| `api/routers/eval_datasets.py` | `POST` | `/{session_id}/eval-datasets/{dataset_id}/baseline` | `set_eval_dataset_baseline` | yes | StageOperationEnvelope or decision-bearing payload | Sets baseline experiment and can unblock `missing_baseline`. |

## Source mapping

The above endpoints delegate to the following service methods in `core/session_service.py`:

```text
create_eval_dataset()
create_eval_dataset_from_stage3()
add_eval_cases_to_dataset()
remove_eval_cases_from_dataset()
set_eval_dataset_baseline()
```

Each method returns `_with_stage_advancement(...)`, which builds a `StageOperationEnvelope` through `build_stage_operation_envelope(...)`.

## Relationship to the contract

`core/stage_advancement_contract.py` declares the relevant Stage 3 resolution operations:

```text
create_eval_dataset_from_stage3
add_eval_cases_to_dataset
set_eval_baseline
create_eval_experiment
run_eval_experiment
compare_eval_experiment
```

Alpha.11 does not change these operations; it corrects the documentation and frontend consumption path around them.
