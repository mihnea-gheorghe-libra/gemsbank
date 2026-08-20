import logging
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, ClassVar, Protocol

from motor.motor_asyncio import AsyncIOMotorClientSession

from backend.accounts.service import (
    Account,
    AccountKind,
    AccountsService,
    get_accounts_service,
    normalise_iban,
)
from backend.command_bus import Command, CommandBus, CommandResult, bus
from backend.config import Settings, settings
from backend.database.records import AuditRecord, DomainEvent
from backend.database.repositories import (
    MongoBeneficiaryRepository,
    MongoPaymentRepository,
)
from backend.helpers.context import ActorContext, log_event
from backend.helpers.crypto import Argon2idHasher
from backend.helpers.errors import DomainError, NotFoundError, ValidationError
from backend.ledger.journal import (
    HouseAccount,
    JournalTransaction,
    TransactionKind,
    house_account_id,
)
from backend.ledger.service import LedgerService, get_ledger_service
from backend.ledger.validation import validate_minor_units
from backend.payments.adapters import (
    DevCodeStepUp,
    InternalPayeeVerifier,
    PolicyDecision,
    PolicyOutcome,
    StaticLimitPolicy,
    SystemClock,
)
from backend.payments.payment import (
    Beneficiary,
    PayeeVerification,
    Payment,
    PaymentStatus,
    SignatureChallenge,
)
from backend.payments.validation import (
    decode_cursor,
    encode_cursor,
    normalise_category,
    normalise_counterparty,
    normalise_direction,
    normalise_reference,
    normalise_search,
    validate_signature_code,
)

logger = logging.getLogger(__name__)

DENIAL_MESSAGES = {
    "over_per_transaction_limit": "That is above the single-payment limit on this account.",
    "over_daily_limit": "That would take you past the payment limit for today.",
}


class MakeTransfer(Command):
    command_name: ClassVar[str] = "payments.transfer"

    source_account_id: str
    target_account_id: str | None = None
    target_iban: str | None = None
    counterparty: str
    amount_minor: int
    reference: str
    category: str | None = None
    acknowledge_payee_mismatch: bool = False


class SignPayment(Command):
    command_name: ClassVar[str] = "payments.transfer.sign"

    payment_id: str
    code: str


class AddBeneficiary(Command):
    command_name: ClassVar[str] = "payments.beneficiary.add"

    name: str
    iban: str


class PaymentRepository(Protocol):
    async def add(
        self, payment: Payment, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...

    async def get(self, payment_id: str) -> Payment | None: ...

    async def save(
        self, payment: Payment, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...

    async def list_by_status(self, user_id: str, status: PaymentStatus) -> list[Payment]: ...

    async def count_by_status(self, user_id: str, status: PaymentStatus) -> int: ...


class BeneficiaryRepository(Protocol):
    async def add(
        self, beneficiary: Beneficiary, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...

    async def list_for_user(self, user_id: str) -> list[Beneficiary]: ...

    async def find(self, user_id: str, iban: str) -> Beneficiary | None: ...


class Policy(Protocol):
    def evaluate(
        self, amount_minor: int, currency: str, spent_today_minor: int
    ) -> PolicyDecision: ...


class StepUp(Protocol):
    async def issue(self, payment_id: str, amount_minor: int, currency: str) -> str: ...


class PayeeVerifier(Protocol):
    async def verify(self, claimed_name: str, holder_name: str | None) -> str: ...


class PasswordHasher(Protocol):
    def hash(self, secret: str) -> str: ...

    def verify(self, secret: str, hashed: str) -> bool: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class PaymentsService:
    def __init__(
        self,
        payments: PaymentRepository,
        beneficiaries: BeneficiaryRepository,
        accounts: AccountsService,
        ledger: LedgerService,
        policy: Policy,
        step_up: StepUp,
        payees: PayeeVerifier,
        hasher: PasswordHasher,
        clock: Clock,
        config: Settings,
    ) -> None:
        self._payments = payments
        self._beneficiaries = beneficiaries
        self._accounts = accounts
        self._ledger = ledger
        self._policy = policy
        self._step_up = step_up
        self._payees = payees
        self._hasher = hasher
        self._clock = clock
        self._config = config

    def register(self, command_bus: CommandBus) -> None:
        command_bus.register(MakeTransfer, self._handle_transfer)
        command_bus.register(SignPayment, self._handle_sign)
        command_bus.register(AddBeneficiary, self._handle_add_beneficiary)

    async def provision_starter_accounts(
        self,
        user_id: str,
        holder_name: str,
        correlation_id: str,
        actor: str,
        session: AsyncIOMotorClientSession | None = None,
    ) -> list[str]:
        opened = await self._accounts.open_starter_accounts(
            user_id, holder_name, session=session
        )
        amount = self._config.demo_opening_balance_minor
        funded = next(
            (account for account in opened if account.kind is AccountKind.CURRENT), None
        )
        if funded is not None and amount > 0:
            await self._deposit_opening_balance(
                funded, amount, correlation_id, actor, session=session
            )
        return [account.id for account in opened]

    async def _deposit_opening_balance(
        self,
        account: Account,
        amount_minor: int,
        correlation_id: str,
        actor: str,
        session: AsyncIOMotorClientSession | None = None,
    ) -> JournalTransaction:
        return await self._ledger.post_transaction(
            currency=account.currency,
            kind=TransactionKind.OPENING_DEPOSIT,
            legs=[
                (account.id, amount_minor),
                (house_account_id(HouseAccount.SETTLEMENT, account.currency), -amount_minor),
            ],
            reference="Demo opening balance",
            counterparty="GEMS demo treasury",
            category="income",
            correlation_id=correlation_id,
            actor=actor,
            session=session,
        )

    def _start_of_day(self) -> datetime:
        return self._clock.now().replace(hour=0, minute=0, second=0, microsecond=0)

    async def _owned_account_ids(self, user_id: str) -> list[str]:
        accounts = await self._accounts.owned_accounts(user_id)
        return [account.id for account in accounts]

    async def _spent_today(self, user_id: str) -> int:
        return await self._ledger.debited_since(
            await self._owned_account_ids(user_id), self._start_of_day()
        )

    async def _load_owned(self, payment_id: str, user_id: str) -> Payment:
        payment = await self._payments.get(payment_id)
        if payment is None or payment.user_id != user_id:
            raise NotFoundError("That payment is not one of yours.")
        return payment

    async def _resolve_target(self, command: MakeTransfer, user_id: str) -> Account:
        if command.target_account_id:
            return await self._accounts.get_owned(command.target_account_id, user_id)
        if not command.target_iban:
            raise ValidationError(
                "Say where the money should go: an IBAN or one of your own accounts.",
                details={"field": "iban"},
            )
        account = await self._accounts.resolve_iban(command.target_iban)
        if account is None:
            raise ValidationError(
                "GEMS can only reach accounts held at GEMS. External rails are not "
                "connected in this demo.",
                details={"field": "iban", "rail": "sepa"},
            )
        return account

    async def _post(
        self,
        payment: Payment,
        source: Account,
        context: ActorContext,
        session: AsyncIOMotorClientSession,
    ) -> JournalTransaction:
        assert payment.target_account_id is not None
        transaction = await self._ledger.transfer(
            source_account_id=source.id,
            target_account_id=payment.target_account_id,
            amount_minor=payment.amount_minor,
            currency=payment.currency,
            reference=payment.reference,
            counterparty=payment.counterparty,
            category=payment.category,
            correlation_id=context.correlation_id,
            actor=context.actor.label(),
            session=session,
        )
        payment.mark_posted(transaction.id)
        return transaction

    def _posted_result(self, payment: Payment, before: str) -> CommandResult:
        after = {
            "status": payment.status.value,
            "journalTransactionId": payment.journal_transaction_id,
            "amountMinorUnits": payment.amount_minor,
            "currency": payment.currency,
        }
        return CommandResult(
            data=payment.receipt_view(),
            audit=AuditRecord(
                action="payments.transfer_posted",
                entity_type="payment",
                entity_id=payment.id,
                before={"status": before},
                after=after,
            ),
            events=[
                DomainEvent(
                    name="payments.transfer_posted",
                    aggregate_type="payment",
                    aggregate_id=payment.id,
                    payload=after,
                )
            ],
        )

    async def _handle_transfer(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, MakeTransfer)
        user_id = context.actor.id

        amount = validate_minor_units(command.amount_minor)
        reference = normalise_reference(command.reference)
        counterparty = normalise_counterparty(command.counterparty)
        category = normalise_category(command.category)

        source = await self._accounts.get_owned(command.source_account_id, user_id)
        source.guard_can_send()

        target = await self._resolve_target(command, user_id)
        source.guard_not_self(target)
        source.guard_same_currency(target)
        target.guard_can_receive()

        balance = await self._ledger.balance_of(source.id)
        source.guard_sufficient(balance, amount)

        decision = self._policy.evaluate(
            amount, source.currency, await self._spent_today(user_id)
        )
        if decision.outcome is PolicyOutcome.DENY:
            raise ValidationError(
                DENIAL_MESSAGES.get(decision.reason, "This payment is outside your limits."),
                details={
                    "field": "amount",
                    "reason": decision.reason,
                    "limitMinorUnits": decision.limit_minor,
                },
            )

        payee_check = PayeeVerification(
            await self._payees.verify(counterparty, target.holder_name)
        )
        if payee_check is PayeeVerification.NO_MATCH and not command.acknowledge_payee_mismatch:
            raise ValidationError(
                "That name does not match the account holder. Check it, then confirm to send.",
                details={"field": "counterparty", "payeeCheck": payee_check.value},
            )

        payment = Payment(
            user_id=user_id,
            source_account_id=source.id,
            target_account_id=target.id,
            target_iban=target.iban,
            counterparty=counterparty,
            amount_minor=amount,
            currency=source.currency,
            reference=reference,
            category=category,
            payee_check=payee_check,
            created_at=self._clock.now(),
        )

        if decision.outcome is PolicyOutcome.REQUIRE_APPROVAL:
            code = await self._step_up.issue(payment.id, amount, source.currency)
            now = self._clock.now()
            payment.require_signature(
                SignatureChallenge(
                    code_hash=self._hasher.hash(code),
                    issued_at=now,
                    expires_at=now + timedelta(seconds=self._config.step_up_code_ttl_seconds),
                )
            )
            await self._payments.add(payment, session=session)
            log_event(
                logger,
                "payments.step_up_required",
                paymentId=payment.id,
                reason=decision.reason,
            )
            return CommandResult(
                data=payment.public_view()
                | {"stepUp": {"required": True, "reason": decision.reason}},
                sensitive={"stepUp": {"required": True, "devCode": code}},
                audit=AuditRecord(
                    action="payments.signature_required",
                    entity_type="payment",
                    entity_id=payment.id,
                    after={
                        "status": payment.status.value,
                        "reason": decision.reason,
                        "amountMinorUnits": amount,
                        "currency": payment.currency,
                    },
                ),
                events=[
                    DomainEvent(
                        name="payments.signature_required",
                        aggregate_type="payment",
                        aggregate_id=payment.id,
                        payload={"reason": decision.reason},
                    )
                ],
            )

        await self._post(payment, source, context, session)
        await self._payments.add(payment, session=session)
        return self._posted_result(payment, PaymentStatus.DRAFT.value)

    async def _handle_sign(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, SignPayment)
        payment = await self._load_owned(command.payment_id, context.actor.id)
        before = payment.status.value

        code = validate_signature_code(command.code)
        challenge = payment.signature
        matches = challenge is not None and self._hasher.verify(code, challenge.code_hash)
        try:
            payment.sign(matches, self._config.step_up_max_attempts, self._clock.now())
        except DomainError:
            await self._payments.save(payment)
            raise

        source = await self._accounts.get_owned(payment.source_account_id, context.actor.id)
        source.guard_can_send()
        balance = await self._ledger.balance_of(source.id)
        source.guard_sufficient(balance, payment.amount_minor)

        await self._post(payment, source, context, session)
        await self._payments.save(payment, session=session)
        return self._posted_result(payment, before)

    async def _handle_add_beneficiary(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, AddBeneficiary)
        user_id = context.actor.id
        name = normalise_counterparty(command.name)
        iban = normalise_iban(command.iban)

        existing = await self._beneficiaries.find(user_id, iban)
        if existing is not None:
            return CommandResult(
                data=existing.public_view(),
                audit=AuditRecord(
                    action="payments.beneficiary_reused",
                    entity_type="beneficiary",
                    entity_id=existing.id,
                    after={"iban": existing.iban},
                ),
            )

        beneficiary = Beneficiary(
            user_id=user_id, name=name, iban=iban, created_at=self._clock.now()
        )
        await self._beneficiaries.add(beneficiary, session=session)
        return CommandResult(
            data=beneficiary.public_view(),
            audit=AuditRecord(
                action="payments.beneficiary_added",
                entity_type="beneficiary",
                entity_id=beneficiary.id,
                after={"name": name, "iban": iban},
            ),
            events=[
                DomainEvent(
                    name="payments.beneficiary_added",
                    aggregate_type="beneficiary",
                    aggregate_id=beneficiary.id,
                )
            ],
        )

    async def list_beneficiaries(self, user_id: str) -> dict[str, Any]:
        found = await self._beneficiaries.list_for_user(user_id)
        return {"beneficiaries": [item.public_view() for item in found]}

    async def list_pending(self, user_id: str) -> dict[str, Any]:
        found = await self._payments.list_by_status(user_id, PaymentStatus.AWAITING_SIGNATURE)
        return {"pending": [item.public_view() for item in found]}

    async def summary(self, user_id: str) -> dict[str, Any]:
        account_ids = await self._owned_account_ids(user_id)
        return {
            "movements": await self._ledger.count_for(account_ids),
            "pendingSignatures": await self._payments.count_by_status(
                user_id, PaymentStatus.AWAITING_SIGNATURE
            ),
        }

    async def list_transactions(
        self,
        user_id: str,
        *,
        direction: str | None = None,
        search: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        account_ids = await self._owned_account_ids(user_id)
        page_size = min(limit or self._config.transactions_page_size, 100)
        rows, next_cursor = await self._ledger.movements(
            account_ids,
            direction=normalise_direction(direction),
            search=normalise_search(search),
            cursor=decode_cursor(cursor),
            limit=page_size,
        )
        return {
            "transactions": rows,
            "nextCursor": encode_cursor(*next_cursor) if next_cursor else None,
        }


@lru_cache(maxsize=1)
def get_payments_service() -> PaymentsService:
    service = PaymentsService(
        payments=MongoPaymentRepository(),
        beneficiaries=MongoBeneficiaryRepository(),
        accounts=get_accounts_service(),
        ledger=get_ledger_service(),
        policy=StaticLimitPolicy(settings),
        step_up=DevCodeStepUp(settings),
        payees=InternalPayeeVerifier(),
        hasher=Argon2idHasher(),
        clock=SystemClock(),
        config=settings,
    )
    service.register(bus)
    return service
