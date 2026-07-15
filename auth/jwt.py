# auth/jwt.py
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel

ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def _secret() -> str:
    try:
        from core.config import settings

        if settings.jwt_secret:
            return settings.jwt_secret
    except Exception:  # noqa: S110  # settings 未就绪时回退到环境变量
        pass
    secret = os.environ.get("JWT_SECRET", "")
    if not secret:
        raise RuntimeError("JWT_SECRET is not configured")
    return secret


class TenantContext(BaseModel):
    user_id: str
    tenant_id: str
    role: str


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    expire = datetime.now(UTC) + (
        expires_delta
        or timedelta(minutes=int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "15")))
    )
    return jwt.encode({**data, "exp": expire, "type": "access"}, _secret(), algorithm=ALGORITHM)


def create_refresh_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(days=int(os.environ.get("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7")))
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


async def get_current_tenant(token: str = Depends(oauth2_scheme)) -> TenantContext:
    return verify_token(token)
