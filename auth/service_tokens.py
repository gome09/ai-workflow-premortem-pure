# auth/service_tokens.py
"""Tenant-scoped machine credentials for the read-only release gate.

Security boundaries:

- The raw token is returned exactly once at creation and is never persisted.
- Only a SHA-256 hash is stored; the token itself has high entropy and is not
  guessable, so password-style KDFs are unnecessary.
- Tokens are tenant-scoped, expiring, revocable, and limited to
  ``release_gate:read``. They cannot approve, write sessions, or read bodies.
- Human access/refresh JWTs never authenticate here.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from storage.session_store import session_store

logger = logging.getLogger(__name__)

SERVICE_TOKEN_PREFIX = "pmgate_"  # noqa: S105  # public token prefix, not a secret
RELEASE_GATE_SCOPE = "release_gate:read"
DEFAULT_TTL_DAYS = 90
MAX_TTL_DAYS = 365

service_token_scheme = HTTPBearer(auto_error=False, scheme_name="ServiceToken")


def hash_service_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_service_token() -> tuple[str, str]:
    """Return ``(raw_token, sha256_hex)``; only the raw token leaves the server once."""
    raw_token = f"{SERVICE_TOKEN_PREFIX}{secrets.token_urlsafe(32)}"
    return raw_token, hash_service_token(raw_token)


def _as_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired service token",
        headers={"WWW-Authenticate": "Bearer"},
    )


class ServiceTokenContext(BaseModel):
    token_id: str
    tenant_id: str
    scope: str


class ServiceTokenService:
    def create(
        self,
        *,
        tenant_id: str,
        name: str,
        expires_in_days: int = DEFAULT_TTL_DAYS,
        created_by: str = "",
    ) -> dict:
        cleaned_name = (name or "").strip()
        if not cleaned_name:
            raise HTTPException(status_code=400, detail="Token name is required")
        if not tenant_id:
            raise HTTPException(status_code=403, detail="Token is missing a tenant scope")
        raw_token, token_hash = generate_service_token()
        now = datetime.now(UTC)
        row = session_store.create_service_token(
            token_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            name=cleaned_name,
            token_hash=token_hash,
            scope=RELEASE_GATE_SCOPE,
            created_by=created_by,
            expires_at=now + timedelta(days=expires_in_days),
        )
        logger.info(
            "service_token_created",
            extra={
                "event": "service_token_created",
                "tenant_id": tenant_id,
                "token_id": row.get("token_id", ""),
                "created_by": created_by or "unknown",
                "expires_at": str(row.get("expires_at", "")),
            },
        )
        return {**row, "token": raw_token}

    def list_tokens(self, tenant_id: str) -> list[dict]:
        return session_store.list_service_tokens_by_tenant(tenant_id)

    def revoke(self, *, tenant_id: str, token_id: str) -> dict:
        try:
            uuid.UUID(token_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Service token not found") from None
        row = session_store.revoke_service_token(
            tenant_id=tenant_id,
            token_id=token_id,
            revoked_at=datetime.now(UTC),
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Service token not found")
        logger.info(
            "service_token_revoked",
            extra={
                "event": "service_token_revoked",
                "tenant_id": tenant_id,
                "token_id": token_id,
            },
        )
        return row

    def authenticate(self, raw_token: str) -> ServiceTokenContext:
        cleaned = (raw_token or "").strip()
        if not cleaned.startswith(SERVICE_TOKEN_PREFIX):
            _log_auth_failure("not_a_service_token", cleaned)
            raise _unauthorized()

        token_hash = hash_service_token(cleaned)
        row = session_store.get_service_token_by_hash(token_hash)
        if row is None:
            _log_auth_failure("not_found", cleaned)
            raise _unauthorized()
        if row.get("revoked_at"):
            _log_auth_failure("revoked", cleaned, token_id=str(row.get("token_id") or ""))
            raise _unauthorized()

        expires_at = _as_datetime(row.get("expires_at"))
        if expires_at is not None and expires_at <= datetime.now(UTC):
            _log_auth_failure("expired", cleaned, token_id=str(row.get("token_id") or ""))
            raise _unauthorized()

        tenant_id = str(row.get("tenant_id") or "")
        if not tenant_id:
            _log_auth_failure("missing_tenant", cleaned, token_id=str(row.get("token_id") or ""))
            raise _unauthorized()
        if row.get("scope") != RELEASE_GATE_SCOPE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Service token scope does not allow release gate access",
            )

        try:
            session_store.touch_service_token(
                str(row["token_id"]),
                tenant_id,
                datetime.now(UTC),
            )
        except Exception:  # pragma: no cover - last-used telemetry must not block auth
            logger.warning(
                "service_token_touch_failed",
                extra={
                    "event": "service_token_touch_failed",
                    "tenant_id": tenant_id,
                    "token_id": str(row.get("token_id") or ""),
                },
                exc_info=True,
            )
        return ServiceTokenContext(
            token_id=str(row["token_id"]),
            tenant_id=tenant_id,
            scope=str(row["scope"]),
        )


def _log_auth_failure(reason: str, raw_token: str, *, token_id: str = "") -> None:
    """Log only a fixed reason, a short hash prefix, and a token id when known."""
    prefix = hash_service_token(raw_token)[:8] if raw_token else ""
    logger.warning(
        "service_token_auth_failed",
        extra={
            "event": "service_token_auth_failed",
            "reason": reason,
            "token_hash_prefix": prefix,
            "token_id": token_id,
        },
    )


service_token_service = ServiceTokenService()


async def get_service_token_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(service_token_scheme),
) -> ServiceTokenContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    return service_token_service.authenticate(credentials.credentials)
