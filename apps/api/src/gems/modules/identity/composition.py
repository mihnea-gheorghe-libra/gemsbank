from functools import lru_cache

from gems.config import settings
from gems.modules.identity.adapters.clock import SystemClock
from gems.modules.identity.adapters.document_extractor import DemoDocumentExtractor
from gems.modules.identity.adapters.hashing import Argon2idHasher
from gems.modules.identity.adapters.mongo_repository import (
    MongoKycCaseRepository,
    MongoUserRepository,
)
from gems.modules.identity.adapters.otp_email import ResendOtpSender
from gems.modules.identity.application.onboarding import (
    ALLOWED_DOC_TYPES,
    MAX_UPLOAD_BYTES,
    OnboardingService,
)
from gems.platform.commandbus.bus import bus


@lru_cache(maxsize=1)
def get_onboarding_service() -> OnboardingService:
    service = OnboardingService(
        cases=MongoKycCaseRepository(),
        users=MongoUserRepository(),
        hasher=Argon2idHasher(),
        otp_sender=ResendOtpSender(settings),
        extractor=DemoDocumentExtractor(ALLOWED_DOC_TYPES, MAX_UPLOAD_BYTES),
        clock=SystemClock(),
        config=settings,
    )
    service.register(bus)
    return service
