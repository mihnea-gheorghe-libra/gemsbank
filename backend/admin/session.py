from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from backend.helpers.context import new_id
from backend.helpers.errors import AuthenticationError

ADMIN_ROLE = "admin"
GENERIC_ADMIN_REJECTION = "That username and password do not match an administrator."


class AdminIdentity(BaseModel):
    id: str
    username: str
    role: str = ADMIN_ROLE

    def public_view(self) -> dict[str, Any]:
        return {"adminId": self.id, "username": self.username, "role": self.role}


class AdminSession(BaseModel):
    id: str = Field(default_factory=new_id)
    admin_id: str
    username: str
    token_hash: str
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    user_agent: str | None = None
    ip_address: str | None = None

    def guard_live(self, now: datetime) -> None:
        if self.revoked_at is not None:
            raise AuthenticationError("You are signed out. Sign in again.")
        if now >= self.expires_at:
            raise AuthenticationError("Your session expired. Sign in again.")

    def revoke(self, now: datetime) -> None:
        if self.revoked_at is None:
            self.revoked_at = now

    def identity(self) -> AdminIdentity:
        return AdminIdentity(id=self.admin_id, username=self.username)

    def public_view(self) -> dict[str, Any]:
        return {"sessionId": self.id, "expiresAt": self.expires_at.isoformat()}
