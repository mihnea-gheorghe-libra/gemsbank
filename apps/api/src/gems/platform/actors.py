from typing import Literal

from pydantic import BaseModel, Field

ActorKind = Literal["user", "system", "agent"]


class Actor(BaseModel):
    kind: ActorKind
    id: str
    on_behalf_of: str | None = None
    mandate_id: str | None = None

    @classmethod
    def public_onboarding(cls) -> "Actor":
        return cls(kind="system", id="public-onboarding")

    @classmethod
    def user(cls, user_id: str) -> "Actor":
        return cls(kind="user", id=user_id)

    def label(self) -> str:
        return f"{self.kind}:{self.id}"


class ActorContext(BaseModel):
    actor: Actor
    correlation_id: str
    ip: str | None = None
    user_agent: str | None = Field(default=None)
