# auth/service.py
from __future__ import annotations

from fastapi import HTTPException, status

from auth.jwt import create_access_token, create_refresh_token, verify_token
from auth.password import hash_password, verify_password
from storage.session_store import session_store


class AuthService:
    def register(self, email: str, password: str, workspace_name: str = "") -> dict:
        """Register new user. First ever user gets admin; subsequent users get viewer."""
        if session_store.get_user_by_email(email):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )
        name = workspace_name or f"{email.split('@')[0]}'s Workspace"
        is_first_user = session_store.count_users() == 0
        default_role = "admin" if is_first_user else "viewer"
        try:
            tenant = session_store.create_tenant(name)
            user = session_store.create_user(
                tenant_id=tenant["tenant_id"],
                email=email,
                password_hash=hash_password(password),
                role=default_role,
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail="Registration failed") from e

        token_data = {
            "sub": user["user_id"],
            "tenant_id": user["tenant_id"],
            "role": user["role"],
        }
        return {
            "user_id": user["user_id"],
            "tenant_id": user["tenant_id"],
            "email": email,
            "role": user["role"],
            "access_token": create_access_token(token_data),
            "refresh_token": create_refresh_token(token_data),
            "token_type": "bearer",
        }

    def login(self, email: str, password: str) -> dict:
        """Verify credentials, return JWT token pair."""
        user = session_store.get_user_by_email(email)
        if not user or not verify_password(password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
            )
        token_data = {
            "sub": user["user_id"],
            "tenant_id": user["tenant_id"],
            "role": user["role"],
        }
        return {
            "user_id": user["user_id"],
            "tenant_id": user["tenant_id"],
            "access_token": create_access_token(token_data),
            "refresh_token": create_refresh_token(token_data),
            "token_type": "bearer",
        }

    def refresh(self, refresh_token: str) -> dict:
        """Exchange refresh_token for new access_token."""
        ctx = verify_token(refresh_token, token_type="refresh")  # noqa: S106  # 令牌类型标签，非密码
        token_data = {"sub": ctx.user_id, "tenant_id": ctx.tenant_id, "role": ctx.role}
        return {
            "access_token": create_access_token(token_data),
            "token_type": "bearer",
        }

    def list_users(self, tenant_id: str) -> list[dict]:
        """List all users in tenant (admin only — enforced at router level)."""
        return [
            {k: str(v) for k, v in u.items() if k != "password_hash"}
            for u in session_store.list_users_by_tenant(tenant_id)
        ]

    def update_role(self, user_id: str, tenant_id: str, new_role: str) -> dict:
        """Update a user's role (admin only — enforced at router level)."""
        from auth.permissions import Role

        try:
            Role(new_role)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid role '{new_role}'. Must be viewer, editor, or admin.",
            )
        updated = session_store.update_user_role(user_id, tenant_id, new_role)
        if not updated:
            raise HTTPException(status_code=404, detail="User not found in this tenant")
        return {k: str(v) for k, v in updated.items()}


auth_service = AuthService()
