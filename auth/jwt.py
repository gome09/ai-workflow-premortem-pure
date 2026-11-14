# auth/jwt.py
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from core.config import settings

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
VALID_ROLES = frozenset({"viewer", "editor", "admin"})
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def _secret() -> str:
    if settings.jwt_secret:
        return settings.jwt_secret
    raise RuntimeError("JWT_SECRET is not configured")


class TenantContext(BaseModel):
    user_id: str
    tenant_id: str
    role: str


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    return jwt.encode({**data, "exp": expire, "type": "access"}, _secret(), algorithm=ALGORITHM)


def create_refresh_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(days=settings.jwt_refresh_token_expire_days)
    )
    return jwt.encode({**data, "exp": expire, "type": "refresh"}, _secret(), algorithm=ALGORITHM)


def verify_token(token: str, token_type: str = "access") -> TenantContext:  # noqa: S107  # 令牌类型标签（access/refresh），非密码
    try:
        payload = jwt.decode(token, _secret(), algorithms=[ALGORITHM])
        if payload.get("type") != token_type:
            raise JWTError(f"Expected token type '{token_type}', got '{payload.get('type')}'")
        return TenantContext(
            user_id=payload["sub"],
            tenant_id=payload["tenant_id"],
            role=payload["role"],
        )
    except (JWTError, KeyError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


def _user_store():
    """Resolve the active session store lazily to avoid import cycles.

    ``core.session_service`` keeps the historical storage patch points used by
    tests and the application facade; production resolves the same singleton.
    """
    from core import session_service as module

    return module.session_store


async def get_current_tenant(token: str = Depends(oauth2_scheme)) -> TenantContext:
    """校验令牌并以数据库当前成员记录作为唯一角色来源。

    空 tenant_id 的令牌无法产生租户过滤，存储层面对空租户会 fail-closed；
    在入口直接 403，避免把越权尝试传成 500 或静默回退到全局读取。
    降权/删除成员必须在下一次请求立即生效，因此 token 内的 role 不再参与授权。
    """
    ctx = verify_token(token)
    if not ctx.tenant_id.strip():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token is missing a tenant scope",
        )

    try:
        user = await run_in_threadpool(_user_store().get_user_by_id, ctx.user_id)
    except Exception as exc:  # noqa: BLE001 - fail closed with a stable 503 contract
        logger.warning(
            "Current-user lookup failed during authentication: user_id=%s tenant_id=%s error=%s",
            ctx.user_id,
            ctx.tenant_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        ) from exc

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_tenant = str(user.get("tenant_id") or "")
    if user_tenant != ctx.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token tenant does not match the current member",
        )

    role = str(user.get("role") or "")
    if role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TenantContext(
        user_id=str(user.get("user_id") or ctx.user_id),
        tenant_id=user_tenant,
        role=role,
    )
