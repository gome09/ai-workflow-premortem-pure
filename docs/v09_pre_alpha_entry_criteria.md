# v0.9-pre-alpha Entry Criteria

Generated: 2026-05-29  
Current package stage: `v0.8.0-alpha.10-source-freeze-check`  
Runtime validation: `deferred_by_instruction`

## Purpose

This document defines the first gate before any v0.9 work starts. It follows the
approved direction: finish alpha.10 stage-advancement source-freeze review before
adding governance scaffolding.

## Entry rule

The project may enter:

```text
v0.9.0-pre-alpha.1-governance-scaffolding
```

only after the alpha.10 source-freeze gate confirms that:

1. `RequiredResolution` values have no drift across readiness, contract, and resolution services.
2. Every current GateRule blocker can map to a `StageResolutionOperation`.
3. Gate-affecting mutating service methods return or expose a refreshed `StageAdvancementDecision`.
4. API routers do not create a second, conflicting stage-advancement contract.
5. Frontend components consume the canonical decision/operation fields.
6. Reports carry a stage advancement snapshot and do not claim runtime validation.
7. Version and delivery docs identify this as source-level pre-validation.

## v0.9-pre-alpha.1 allowed work

Only low-coupling scaffolding is allowed:

```text
Workspace model scaffold
Project model scaffold
optional Session workspace_id / project_id fields
RBAC enum / permission scaffold
Claim model scaffold
ClaimEvidenceLink model scaffold
ReportArtifact status field scaffold
API docs scaffolding
```

## v0.9-pre-alpha.1 prohibited work

Do not implement or enforce yet:

```text
mandatory Project ownership for all sessions
full RBAC on every router
multi-tenant data isolation
Claim-Evidence Graph gate blockers
Report approval / publish workflow as a hard gate
production authentication / authorization
LangGraph interrupt as the primary runner
real LLM-as-judge execution
```

## If the freeze gate fails

Do not enter v0.9. Create a small repair package instead:

```text
v0.8.0-alpha.11-freeze-fix
```

with only the specific contract, API return, frontend consumption, or report metadata fixes needed.
