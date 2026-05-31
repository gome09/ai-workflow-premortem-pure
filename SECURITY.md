# Security Policy

> **Current release / acceptance label:** `v0.8.0-beta.1-local-preview-final`  
> **Security status:** Local-preview only. Not production-ready.

This project can be used for personal or trusted small-team local analysis, but it is not hardened for public, enterprise, multi-tenant, or regulated production deployment.

---

## Supported Status

The current maintained package state is:

| Item | Value |
|------|-------|
| Source version | `0.8.0-alpha.11` |
| Release / acceptance label | `v0.8.0-beta.1-local-preview-final` |
| Accepted scope | Personal / small-team Docker local preview |
| Production status | **NOT production-ready** |

Security-sensitive outputs must be reviewed by humans before real-world use.

---

## Current Security Limitations

The current local-preview build does not provide production-grade controls:

- No authentication
- No authorization / RBAC
- No multi-tenant isolation
- No rate limiting or abuse prevention
- No production secrets management
- No production observability, alerting, or incident workflow
- No load/concurrency hardening
- CORS is permissive for local-preview use
- Docker Compose exposes local service ports for development convenience
- The built-in safety layer is lightweight and not a full LLM red-team framework

Do not expose this service directly to the public internet.

---

## Credential Handling

Never commit or share:

- `.env`
- Real DeepSeek API keys
- Real Tavily API keys
- Database passwords
- Raw runtime exports containing credentials or sensitive project data

Live E2E reports in this package should contain only redacted credential markers. If a previous package containing credential fragments was shared, rotate the affected DeepSeek, Tavily, and database credentials before continued use.

---

## Recommended Local Use Rules

For personal or trusted small-team use:

1. Run only on localhost or a trusted private network.
2. Keep `.env` outside version control.
3. Use strong local database passwords.
4. Do not enter sensitive personal, customer, medical, legal, or financial data unless you have an independent governance process.
5. Manually review all AI-generated outputs before acting on them.
6. Treat high-risk or regulated use cases as blocked unless reviewed by qualified humans.

---

## Required Before Production Use

Before any public or production deployment, add at minimum:

- Authentication
- Authorization / RBAC
- Tenant isolation
- Restricted CORS configuration
- Network-level access controls
- Secrets manager integration
- Rate limiting
- Audit log retention policy
- Monitoring, alerting, and incident response
- Load/concurrency testing
- Data retention and deletion controls
- Security review for prompt injection and tool-use abuse
- Independent review for regulated domains

---

## Reporting Vulnerabilities

Please open a private security advisory or contact the maintainers directly. Do not publish exploit details before maintainers have had time to respond.
