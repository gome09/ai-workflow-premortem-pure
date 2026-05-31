# v0.6.0-alpha.7 Stage Advancement Operation Hardening

This document describes the alpha.7 hardening layer built on top of the existing alpha.6 Stage Advancement Contract Closure. It does not redesign the product.

## Objective

Make every current blocker map to a real, accurate, non-misleading next operation.

```text
StageBlocker -> StageResolutionOperation -> executable API or explicit chat/revise path
```

## Rules

1. Future stages remain visible as placeholders but do not add `missing_stage_output` to current required operations.
2. `StageResolutionOperation.api_path` can point to `/actions/{action_id}/resolve` only when the action is still pending.
3. Resolved, superseded, or cancelled actions are audit history only and appear under metadata, not as executable API bindings.
4. Parser, policy-gap, and evidence-gap edit actions must include structured stage output.
5. Missing or unknown evidence ids require structured Stage 1 edit; existing unverified evidence ids require evidence verification.
6. Stage 4 final governance wraps unresolved upstream hard blockers before completion.

## Validation status

Runtime validation remains deferred by instruction. Do not treat this package as beta or production-ready until the unified validation pass is completed.
