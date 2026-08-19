import asyncio
import hashlib
import logging
from datetime import date, datetime, timezone

from argon2 import PasswordHasher as Argon2PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

from backend.config import Settings
from backend.helpers.context import log_event
from backend.helpers.errors import DeliveryError, ValidationError
from backend.onboarding.kyc import ExtractedIdentity

logger = logging.getLogger(__name__)

ALLOWED_DOC_TYPES = {"ci_front", "passport"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024

SYNTHETIC_NAMES = [
    "POP ANDREI-MIHAI",
    "IONESCU MARIA-ELENA",
    "DUMITRU RADU-STEFAN",
    "GEORGESCU ANA-CRISTINA",
    "MARINESCU VLAD-NICOLAE",
    "STOICA IOANA-GABRIELA",
    "PETRESCU DAN-ALEXANDRU",
    "CONSTANTIN LAURA-MIHAELA",
]

SERIES = ["XZ", "RK", "TB", "MM", "AS", "GL", "CJ", "IF"]

MINOR_IN_ONE_OF = 8


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class Argon2idHasher:
    def __init__(self) -> None:
        self._hasher = Argon2PasswordHasher()

    def hash(self, secret: str) -> str:
        return self._hasher.hash(secret)

    def verify(self, secret: str, hashed: str) -> bool:
        try:
            return self._hasher.verify(hashed, secret)
        except (VerifyMismatchError, VerificationError):
            return False


def _cnp_gender_digit(birth_year: int, is_female: bool) -> int:
    if birth_year >= 2000:
        return 6 if is_female else 5
    return 2 if is_female else 1


class DemoDocumentExtractor:
    def __init__(
        self,
        allowed_types: set[str] = ALLOWED_DOC_TYPES,
        max_bytes: int = MAX_UPLOAD_BYTES,
    ) -> None:
        self._allowed_types = allowed_types
        self._max_bytes = max_bytes

    async def extract(self, doc_type: str, content: bytes, filename: str) -> ExtractedIdentity:
        if doc_type not in self._allowed_types:
            raise ValidationError(
                "Unsupported document type.",
                details={"field": "docType", "allowed": sorted(self._allowed_types)},
            )
        if not content:
            raise ValidationError("The uploaded file is empty.", details={"field": "file"})
        if len(content) > self._max_bytes:
            raise ValidationError(
                "The file is larger than 5 MB.",
                details={"field": "file", "maxBytes": self._max_bytes},
            )

        digest = hashlib.sha256(content + filename.encode("utf-8")).digest()
        name = SYNTHETIC_NAMES[digest[0] % len(SYNTHETIC_NAMES)]
        series = SERIES[digest[1] % len(SERIES)]

        today = date.today()
        if digest[10] % MINOR_IN_ONE_OF == 0:
            birth_year = today.year - 17 + digest[2] % 4
        else:
            birth_year = today.year - 66 + digest[2] % 45
        birth_month = 1 + digest[3] % 12
        birth_day = 1 + digest[4] % 28
        birth_date = date(birth_year, birth_month, birth_day)

        gender_digit = _cnp_gender_digit(birth_year, bool(digest[5] % 2))
        cnp_prefix = f"{gender_digit}{str(birth_year)[2:]}{birth_month:02d}"

        expires_on = date(
            today.year + 3 + digest[6] % 5,
            1 + digest[7] % 12,
            1 + digest[8] % 28,
        )

        return ExtractedIdentity(
            full_name=name,
            birth_date=birth_date,
            cnp_masked=f"{cnp_prefix}••••••••",
            document_number_masked=f"{series} ••••{digest[9] % 100:02d}",
            expires_on=expires_on,
        )


class ResendOtpSender:
    def __init__(self, config: Settings) -> None:
        self._config = config

    async def send(self, email: str, code: str, expires_at: datetime) -> None:
        if not self._config.resend_api_key:
            log_event(logger, "otp.not_sent_no_api_key", to=email)
            return

        import resend

        resend.api_key = self._config.resend_api_key
        minutes = max(int((expires_at - datetime.now(expires_at.tzinfo)).total_seconds() // 60), 1)
        html = (
            '<div style="font-family:Barlow,Arial,sans-serif;color:#280725">'
            '<h2 style="color:#450C3F">GEMS</h2>'
            f'<p>Codul tău de verificare este: <strong style="font-size:22px">{code}</strong></p>'
            f"<p>Expiră în {minutes} minute. Dacă nu ai cerut tu acest cod, ignoră mesajul.</p>"
            "</div>"
        )
        try:
            await asyncio.to_thread(
                resend.Emails.send,
                {
                    "from": self._config.otp_from_email,
                    "to": email,
                    "subject": "Codul tău GEMS",
                    "html": html,
                },
            )
        except Exception as exc:
            log_event(logger, "otp.send_failed", to=email, reason=str(exc))
            raise DeliveryError(
                "We could not send the code to that address. Check it and try again.",
                details={"field": "email"},
            ) from exc
        log_event(logger, "otp.sent", to=email)
