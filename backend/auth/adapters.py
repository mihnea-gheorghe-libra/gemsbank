import asyncio
import ipaddress
import logging
import re
from datetime import datetime, timezone

from backend.config import Settings
from backend.helpers.context import log_event
from backend.helpers.errors import DeliveryError

logger = logging.getLogger(__name__)

_OS_PATTERNS = [
    (re.compile(r"iphone", re.IGNORECASE), "iPhone"),
    (re.compile(r"ipad", re.IGNORECASE), "iPad"),
    (re.compile(r"android", re.IGNORECASE), "Android"),
    (re.compile(r"windows", re.IGNORECASE), "Windows"),
    (re.compile(r"mac ?os", re.IGNORECASE), "macOS"),
    (re.compile(r"linux", re.IGNORECASE), "Linux"),
]

_BROWSER_PATTERNS = [
    (re.compile(r"edg/", re.IGNORECASE), "Edge"),
    (re.compile(r"opr/|opera", re.IGNORECASE), "Opera"),
    (re.compile(r"chrome/", re.IGNORECASE), "Chrome"),
    (re.compile(r"crios/", re.IGNORECASE), "Chrome"),
    (re.compile(r"firefox/", re.IGNORECASE), "Firefox"),
    (re.compile(r"safari/", re.IGNORECASE), "Safari"),
]


def describe_device(user_agent: str | None) -> str:
    if not user_agent:
        return "Unknown device"
    browser = next((label for pattern, label in _BROWSER_PATTERNS if pattern.search(user_agent)), None)
    system = next((label for pattern, label in _OS_PATTERNS if pattern.search(user_agent)), None)
    if browser and system:
        return f"{browser} on {system}"
    return browser or system or "Unknown device"


def classify_location(ip_address: str | None) -> str:
    if not ip_address:
        return "Unknown location"
    try:
        parsed = ipaddress.ip_address(ip_address)
    except ValueError:
        return "Unknown location"
    if parsed.is_loopback or parsed.is_private:
        return "Local network"
    return "Unknown location"


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class ResendResetCodeSender:
    def __init__(self, config: Settings) -> None:
        self._config = config

    async def send(
        self,
        email: str,
        code: str,
        expires_at: datetime,
        purpose: str = "resetarea parolei",
        subject: str = "Resetare parolă GEMS",
    ) -> None:
        if not self._config.resend_api_key:
            log_event(logger, "reset_code.not_sent_no_api_key", to=email)
            return

        import resend

        resend.api_key = self._config.resend_api_key
        minutes = max(int((expires_at - datetime.now(expires_at.tzinfo)).total_seconds() // 60), 1)
        html = (
            '<div style="font-family:Barlow,Arial,sans-serif;color:#280725">'
            '<h2 style="color:#450C3F">GEMS</h2>'
            f"<p>Ai cerut {purpose}. Codul tău este: "
            f'<strong style="font-size:22px">{code}</strong></p>'
            f"<p>Expiră în {minutes} minute. Dacă nu ai cerut tu această acțiune, ignoră mesajul "
            "— contul tău rămâne neschimbat.</p>"
            "</div>"
        )
        try:
            await asyncio.to_thread(
                resend.Emails.send,
                {
                    "from": self._config.otp_from_email,
                    "to": email,
                    "subject": subject,
                    "html": html,
                },
            )
        except Exception as exc:
            log_event(logger, "reset_code.send_failed", to=email, reason=str(exc))
            raise DeliveryError(
                "We could not send the code to the address on file. Try again shortly.",
                details={"field": "username"},
            ) from exc
        log_event(logger, "reset_code.sent", to=email)
