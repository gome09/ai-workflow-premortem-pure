# Second Public Edition

> **Release label:** `v0.8.0-beta.1-local-preview-final`
> **Source version:** `0.8.0-alpha.11`

---

## What is this?

This is the **second public edition** of the AI Workflow Pre-mortem & Human Oversight Platform.

The first public edition was published separately and remains available in its own repository. This second edition is an independent source release that should be treated as a distinct publication — it does not overwrite, replace, or supersede the first edition.

---

## Edition Relationship

| Item | First Edition | Second Edition (this) |
|------|---------------|----------------------|
| Repository | Separate repository | This repository |
| Status | Standalone | Standalone |
| Overwrite | No — both editions coexist | No — both editions coexist |

If you are looking for the first edition, consult its original repository. This document exists to prevent confusion between the two.

---

## Intended Use

This release is suitable for:

- **Personal local use** — running on your own machine for AI project pre-mortem analysis
- **Trusted small-team internal preview** — 2–5 person teams on a private network
- **Evaluation and experimentation** — exploring the workflow engine, safety gates, and human oversight patterns

---

## Explicit Non-Goals

This release is **NOT**:

- **Production-ready** — no authentication, no authorization, no multi-tenant isolation
- **SaaS-ready** — no billing, no user management, no tenant provisioning
- **Multi-tenant-ready** — no data isolation between users or teams
- **Internet-facing** — do not expose this service directly to the public internet

---

## Security Boundary

Run this platform only on **localhost** or a **trusted private network**. Do not deploy it to a public server, VPS, or cloud instance without first adding proper authentication, authorization, and network-level access controls.

See [SECURITY.md](SECURITY.md) for the full security policy.

---

## What Has Been Validated

| Check | Result |
|-------|--------|
| Docker environment (postgres, redis) | PASS |
| 13 acceptance scripts (707 checks) | PASS |
| 148 pytest tests | PASS |
| Real E2E with DeepSeek + Tavily | PASS (low-risk scenarios) |
| Risk-adaptive Stage 3 gate | Validated |

See [docs/current_project_state.md](docs/current_project_state.md) for the authoritative project status.

---

## Related Documents

| Document | Purpose |
|----------|---------|
| [README.md](README.md) | Project overview and quick start |
| [SECURITY.md](SECURITY.md) | Security policy and limitations |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contribution guidelines |
| [SUPPORT.md](SUPPORT.md) | Support policy |
| [CLAUDE.md](CLAUDE.md) | Development constraints |
