import logging
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel

from backend.config import Settings
from backend.helpers.context import log_event

logger = logging.getLogger(__name__)


class PolicyOutcome(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


class PolicyDecision(BaseModel):
    outcome: PolicyOutcome
    reason: str
    limit_minor: int | None = None


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class StaticLimitPolicy:
    def __init__(self, config: Settings) -> None:
        self._config = config

    def evaluate(
        self, amount_minor: int, currency: str, spent_today_minor: int
    ) -> PolicyDecision:
        per_transaction = self._config.payment_per_transaction_limit_minor
        if amount_minor > per_transaction:
            return PolicyDecision(
                outcome=PolicyOutcome.DENY,
                reason="over_per_transaction_limit",
                limit_minor=per_transaction,
            )

        daily = self._config.payment_daily_limit_minor
        if spent_today_minor + amount_minor > daily:
            return PolicyDecision(
                outcome=PolicyOutcome.DENY, reason="over_daily_limit", limit_minor=daily
            )

        threshold = self._config.payment_step_up_threshold_minor
        if amount_minor > threshold:
            return PolicyDecision(
                outcome=PolicyOutcome.REQUIRE_APPROVAL,
                reason="over_step_up_threshold",
                limit_minor=threshold,
            )

        return PolicyDecision(outcome=PolicyOutcome.ALLOW, reason="within_limits")


class DevCodeStepUp:
    def __init__(self, config: Settings) -> None:
        self._config = config

    async def issue(self, payment_id: str, amount_minor: int, currency: str) -> str:
        code = self._config.step_up_dev_code
        log_event(
            logger,
            "step_up.challenge_issued",
            paymentId=payment_id,
            amountMinorUnits=amount_minor,
            currency=currency,
            adapter="dev_code_stub",
        )
        return code


class InternalPayeeVerifier:
    async def verify(self, claimed_name: str, holder_name: str | None) -> str:
        from backend.payments.payment import PayeeVerification
        from backend.payments.validation import names_agree

        if holder_name is None:
            return PayeeVerification.NOT_CHECKED.value
        if claimed_name.strip().lower() == holder_name.strip().lower():
            return PayeeVerification.MATCH.value
        if names_agree(claimed_name, holder_name):
            return PayeeVerification.CLOSE_MATCH.value
        return PayeeVerification.NO_MATCH.value
