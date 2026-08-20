import asyncio
import logging
from datetime import datetime, timezone

from backend.config import Settings
from backend.helpers.context import log_event
from backend.helpers.errors import DeliveryError

logger = logging.getLogger(__name__)


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class ResendResetCodeSender:
    def __init__(self, config: Settings) -> None:
        self._config = config

    async def send(self, email: str, code: str, expires_at: datetime) -> None:
        if not self._config.resend_api_key:
            log_event(logger, "reset_code.not_sent_no_api_key", to=email)
            return

        import resend

        resend.api_key = self._config.resend_api_key
        minutes = max(int((expires_at - datetime.now(expires_at.tzinfo)).total_seconds() // 60), 1)
        html = (
            '<div style="font-family:Barlow,Arial,sans-serif;color:#280725">'
            '<h2 style="color:#450C3F">GEMS</h2>'
            "<p>Ai cerut resetarea parolei. Codul tău este: "
            f'<strong style="font-size:22px">{code}</strong></p>'
            f"<p>Expiră în {minutes} minute. Dacă nu ai cerut tu resetarea, ignoră mesajul "
            "— parola ta rămâne neschimbată.</p>"
            "</div>"
        )
        try:
            await asyncio.to_thread(
                resend.Emails.send,
                {
                    "from": self._config.otp_from_email,
                    "to": email,
                    "subject": "Resetare parolă GEMS",
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
