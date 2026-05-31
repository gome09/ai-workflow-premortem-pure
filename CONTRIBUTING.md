# Contributing

Thanks for contributing to AI Workflow Tool.

## Development workflow

1. Install dependencies with `make install-dev`.
2. Start local services with `make dev-db`.
3. Run static checks before opening a PR.
4. Keep AI-generated outputs reviewable, auditable, and schema-first.

## Design constraints

- Do not turn this project into a generic workflow builder.
- Keep the default execution path deterministic and `single_step`.
- Human oversight actions must be explicit and auditable.
- Eval changes must preserve existing EvalCase definitions and add EvalRun records
  for concrete executions.

### Recommended local setup

For a reproducible development environment, use:

```bash
uv sync --all-extras --frozen
```

The `make install-dev` target is provided as a convenience wrapper for the same development setup.

