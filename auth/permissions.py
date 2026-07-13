# auth/permissions.py
from __future__ import annotations

from enum import StrEnum

from fastapi import Depends, HTTPException, status

from auth.jwt import TenantContext, get_current_tenant


class Role(StrEnum):
    viewer = "viewer"
    editor = "editor"
    admin = "admin"


def require_roles(*roles: Role):
    """FastAPI dependency factory: raises 403 if current user's role is not in `roles`."""

    async def _check(tenant: TenantContext = Depends(get_current_tenant)) -> TenantContext:
        try:
            current_role = Role(tenant.role)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Unknown role: {tenant.role}",
            )
        if current_role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return tenant

    return Depends(_check)
