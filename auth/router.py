# auth/router.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from api.limiter import limiter
from auth.jwt import TenantContext, get_current_tenant
from auth.permissions import Role, require_roles
from auth.service import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str
    password: str
    workspace_name: str = ""


class RefreshRequest(BaseModel):
    refresh_token: str


class UpdateRoleRequest(BaseModel):
    role: str


@router.post("/register")
@limiter.limit("5/hour")
def register(request: Request, body: RegisterRequest) -> dict:
    """Register new user. First user gets admin; subsequent users get viewer."""
    return auth_service.register(body.email, body.password, body.workspace_name)


@router.post("/login")
@limiter.limit("10/minute")
def login(request: Request, form: OAuth2PasswordRequestForm = Depends()) -> dict:
    """Login, returns access_token + refresh_token. Use email in username field."""
    return auth_service.login(form.username, form.password)


@router.post("/refresh")
def refresh(body: RefreshRequest) -> dict:
    """Exchange refresh_token for new access_token."""
    return auth_service.refresh(body.refresh_token)


@router.get("/users", dependencies=[require_roles(Role.admin)])
def list_users(ctx: TenantContext = Depends(get_current_tenant)) -> list[dict]:
    """List all users in the current tenant. Admin only."""
    return auth_service.list_users(ctx.tenant_id)


@router.patch("/users/{user_id}/role", dependencies=[require_roles(Role.admin)])
def update_user_role(
    user_id: str,
    body: UpdateRoleRequest,
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    """Update a user's role within the current tenant. Admin only."""
    return auth_service.update_role(user_id, ctx.tenant_id, body.role)
