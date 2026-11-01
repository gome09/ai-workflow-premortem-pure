# auth/service.py
from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status

from auth.jwt import create_access_token, create_refresh_token, verify_token
from auth.password import hash_password, verify_password
from storage.session_store import session_store

INVITATION_TTL = timedelta(days=7)
_INVITATION_ROLES = {"viewer", "editor", "admin"}


def _hash_invitation_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


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


class AuthService:
    def register(self, email: str, password: str, workspace_name: str = "") -> dict:
        """Create a workspace; its creator is always the workspace admin."""
        if session_store.get_user_by_email(email):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )
        name = workspace_name or f"{email.split('@')[0]}'s Workspace"
        try:
            tenant = session_store.create_tenant(name)
            user = session_store.create_user(
                tenant_id=tenant["tenant_id"],
                email=email,
                password_hash=hash_password(password),
                role="admin",
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
        """Exchange refresh_token for a new access token using current member role."""
        ctx = verify_token(refresh_token, token_type="refresh")  # noqa: S106  # 令牌类型标签，非密码
        user = session_store.get_user_by_id(ctx.user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )
        role = str(user.get("role") or "")
        if role not in _INVITATION_ROLES:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )
        token_data = {
            "sub": user["user_id"],
            "tenant_id": user["tenant_id"],
            "role": role,
        }
        return {
            "user_id": user["user_id"],
            "tenant_id": user["tenant_id"],
            "role": role,
            "access_token": create_access_token(token_data),
            "token_type": "bearer",
        }

    def create_invitation(
        self,
        tenant_id: str,
        email: str,
        role: str,
        invited_by: str,
    ) -> dict:
        """Create a one-time workspace invitation; the raw token is returned once."""
        normalized_email = email.strip().lower()
        if not normalized_email or "@" not in normalized_email:
            raise HTTPException(status_code=400, detail="A valid email is required")
        if role not in _INVITATION_ROLES:
            raise HTTPException(
                status_code=422,
                detail="Invalid role. Must be viewer, editor, or admin.",
            )
        if session_store.get_user_by_email(normalized_email):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )
        now = datetime.now(UTC)
        for existing in session_store.list_invitations_by_tenant(tenant_id):
            if (
                existing.get("email", "").lower() == normalized_email
                and existing.get("status") == "pending"
            ):
                expires = _as_datetime(existing.get("expires_at"))
                if expires is None or expires > now:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="A pending invitation already exists for this email",
                    )

        token = secrets.token_urlsafe(32)
        invitation = session_store.create_invitation(
            tenant_id=tenant_id,
            email=normalized_email,
            role=role,
            token_hash=_hash_invitation_token(token),
            invited_by=invited_by,
            expires_at=now + INVITATION_TTL,
        )
        invitation["token"] = token
        return invitation

    def list_invitations(self, tenant_id: str) -> list[dict]:
        return session_store.list_invitations_by_tenant(tenant_id)

    def accept_invitation(self, token: str, password: str) -> dict:
        """Accept an invitation, create the invited user, and return a token pair."""
        if not token or not password:
            raise HTTPException(status_code=400, detail="token and password are required")
        invitation = session_store.get_invitation_by_token_hash(_hash_invitation_token(token))
        if invitation is None or invitation.get("status") != "pending":
            raise HTTPException(status_code=400, detail="Invitation is invalid or already used")
        expires = _as_datetime(invitation.get("expires_at"))
        if expires is None or expires <= datetime.now(UTC):
            raise HTTPException(status_code=400, detail="Invitation has expired")
        if session_store.get_user_by_email(invitation["email"]):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )
        try:
            user = session_store.accept_invitation(
                invitation_id=invitation["invitation_id"],
                password_hash=hash_password(password),
                accepted_at=datetime.now(UTC),
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Invitation could not be accepted",
            ) from exc
        if not user:
            raise HTTPException(status_code=409, detail="Invitation is invalid or already used")

        token_data = {
            "sub": user["user_id"],
            "tenant_id": user["tenant_id"],
            "role": user["role"],
        }
        return {
            "user_id": user["user_id"],
            "tenant_id": user["tenant_id"],
            "email": user["email"],
            "role": user["role"],
            "access_token": create_access_token(token_data),
            "refresh_token": create_refresh_token(token_data),
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
