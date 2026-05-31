# Security Model

This project uses a lightweight safety layer for alpha-stage review workflows.

## SafetyFinding Types

- `prompt_injection`
- `sensitive_info`
- `unsupported_claim`
- `over_autonomy`
- `unsafe_instruction`
- `source_untrusted`
- `policy_gap`

## Blocking Behavior

High and critical findings with `requires_human_review=true` are converted into blocking `PendingHumanAction` records by the review gate.

## Current Limits

- Rules are intentionally lightweight and deterministic.
- `unsupported_claim` is based on strong assertion phrases without nearby evidence IDs.
- `policy_gap` is inferred from high-risk workflow nodes or trigger methods missing human review.
- This is not a replacement for a complete security review or production policy engine.
