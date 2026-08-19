import asyncio
import logging
from datetime import datetime

from gems.config import Settings
from gems.platform.errors import DeliveryError
from gems.platform.observability.correlation import log_event

logger = logging.getLogger(__name__)


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
            "<div style=\"font-family:Barlow,Arial,sans-serif;color:#280725\">"
            "<h2 style=\"color:#450C3F\">GEMS</h2>"
            f"<p>Codul tău de verificare este: <strong style=\"font-size:22px\">{code}</strong></p>"
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
