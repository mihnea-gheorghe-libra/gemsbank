from datetime import datetime
from typing import Protocol

from motor.motor_asyncio import AsyncIOMotorClientSession

from gems.modules.identity.domain.kyc import ExtractedIdentity, KycCase


class KycCaseRepository(Protocol):
    async def add(self, case: KycCase, session: AsyncIOMotorClientSession | None = None) -> None: ...

    async def get(self, case_id: str) -> KycCase | None: ...

    async def save(
        self, case: KycCase, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...


class UserRepository(Protocol):
    async def create(
        self,
        user_id: str,
        username: str,
        email: str,
        phone: str,
        password_hash: str,
        pin_hash: str,
        kyc_case_id: str,
        session: AsyncIOMotorClientSession | None = None,
    ) -> None: ...

    async def exists_username(self, username: str) -> bool: ...

    async def exists_email(self, email: str) -> bool: ...


class PasswordHasher(Protocol):
    def hash(self, secret: str) -> str: ...

    def verify(self, secret: str, hashed: str) -> bool: ...


class OtpSender(Protocol):
    async def send(self, email: str, code: str, expires_at: datetime) -> None: ...


class DocumentExtractor(Protocol):
    async def extract(self, doc_type: str, content: bytes, filename: str) -> ExtractedIdentity: ...


class Clock(Protocol):
    def now(self) -> datetime: ...
