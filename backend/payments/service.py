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
from backend.auth.service import AuthService, get_auth_service
from backend.command_bus import Command, CommandBus, CommandResult, bus
from backend.config import Settings, settings
from backend.database.records import AuditRecord, DomainEvent
from backend.database.repositories import (
    MongoBeneficiaryRepository,
    MongoPaymentRepository,
    MongoPaymentTemplateRepository,
)
from backend.exchange.service import ExchangeService, get_exchange_service
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
from backend.ledger.validation import normalise_currency, validate_minor_units
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
    PaymentTemplate,
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
    normalise_template_name,
    validate_signature_code,
)

logger = logging.getLogger(__name__)

DENIAL_MESSAGES = {
    "over_per_transaction_limit": "That is above the single-payment limit on this account.",
    "over_daily_limit": "That would take you past the payment limit for today.",
}

UNLIMITED_SIGN_ATTEMPTS = 2**31


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


class AddFunds(Command):
    command_name: ClassVar[str] = "payments.add_funds"

    account_id: str
    amount_minor: int


class AddTemplate(Command):
    command_name: ClassVar[str] = "payments.template.add"

    name: str
    beneficiary: str
    iban: str
    currency: str
    reference: str


class UpdateTemplate(Command):
    command_name: ClassVar[str] = "payments.template.update"

    template_id: str
    name: str
    beneficiary: str
    iban: str
    currency: str
    reference: str


class DeleteTemplate(Command):
    command_name: ClassVar[str] = "payments.template.delete"

    template_id: str


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

    async def ibans_by_journal_transaction_ids(
        self, journal_transaction_ids: list[str]
    ) -> dict[str, str]: ...


class BeneficiaryRepository(Protocol):
    async def add(
        self, beneficiary: Beneficiary, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...

    async def list_for_user(self, user_id: str) -> list[Beneficiary]: ...

    async def find(self, user_id: str, iban: str) -> Beneficiary | None: ...


class PaymentTemplateRepository(Protocol):
    async def add(
        self, template: PaymentTemplate, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...

    async def list_for_user(self, user_id: str) -> list[PaymentTemplate]: ...

    async def get(self, template_id: str) -> PaymentTemplate | None: ...

    async def update(
        self, template: PaymentTemplate, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...

    async def delete(
        self, template_id: str, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...


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
        templates: PaymentTemplateRepository,
        accounts: AccountsService,
        ledger: LedgerService,
        exchange: ExchangeService,
        policy: Policy,
        step_up: StepUp,
        payees: PayeeVerifier,
        hasher: PasswordHasher,
        auth: AuthService,
        clock: Clock,
        config: Settings,
    ) -> None:
        self._payments = payments
        self._beneficiaries = beneficiaries
        self._templates = templates
        self._accounts = accounts
        self._ledger = ledger
        self._exchange = exchange
        self._policy = policy
        self._step_up = step_up
        self._payees = payees
        self._hasher = hasher
        self._auth = auth
        self._clock = clock
        self._config = config

    def register(self, command_bus: CommandBus) -> None:
        command_bus.register(MakeTransfer, self._handle_transfer)
        command_bus.register(SignPayment, self._handle_sign)
        command_bus.register(AddBeneficiary, self._handle_add_beneficiary)
        command_bus.register(AddFunds, self._handle_add_funds)
        command_bus.register(AddTemplate, self._handle_add_template)
        command_bus.register(UpdateTemplate, self._handle_update_template)
        command_bus.register(DeleteTemplate, self._handle_delete_template)

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
        if payment.target_currency and payment.target_currency != payment.currency:
            result = await self._exchange.bridge(
                session=session,
                context=context,
                source_account_id=source.id,
                target_account_id=payment.target_account_id,
                amount_minor=payment.amount_minor,
                source_currency=payment.currency,
                target_currency=payment.target_currency,
                reference=payment.reference,
                counterparty=payment.counterparty,
                category=payment.category,
            )
            payment.record_conversion(result.target_amount_minor, result.rate_micro)
            payment.mark_posted(result.source_transaction.id)
            return result.source_transaction

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

        if command.target_account_id:
            payee_check = PayeeVerification.MATCH
        else:
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
            target_currency=target.currency if target.currency != source.currency else None,
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

        pin = validate_signature_code(command.code)
        matches = payment.signature is not None and await self._auth.verify_user_pin(
            context.actor.id, pin
        )
        try:
            payment.sign(matches, UNLIMITED_SIGN_ATTEMPTS, self._clock.now())
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

    async def _handle_add_funds(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, AddFunds)
        user_id = context.actor.id
        amount = validate_minor_units(command.amount_minor)

        account = await self._accounts.get_owned(command.account_id, user_id)
        account.guard_can_receive()

        balance_before = await self._ledger.balance_of(account.id)
        transaction = await self._ledger.post_transaction(
            currency=account.currency,
            kind=TransactionKind.DEMO_TOPUP,
            legs=[
                (account.id, amount),
                (house_account_id(HouseAccount.SETTLEMENT, account.currency), -amount),
            ],
            reference="Demo top-up",
            counterparty="GEMS demo treasury",
            category="income",
            correlation_id=context.correlation_id,
            actor=context.actor.label(),
            session=session,
        )

        after = {
            "accountId": account.id,
            "amountMinorUnits": amount,
            "currency": account.currency,
            "journalTransactionId": transaction.id,
        }
        return CommandResult(
            data=account.public_view(balance_before + amount),
            audit=AuditRecord(
                action="payments.funds_added",
                entity_type="account",
                entity_id=account.id,
                after=after,
            ),
            events=[
                DomainEvent(
                    name="payments.funds_added",
                    aggregate_type="account",
                    aggregate_id=account.id,
                    payload=after,
                )
            ],
        )

    async def _load_owned_template(self, template_id: str, user_id: str) -> PaymentTemplate:
        template = await self._templates.get(template_id)
        if template is None or template.user_id != user_id:
            raise NotFoundError("That template is not one of yours.")
        return template

    async def _handle_add_template(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, AddTemplate)
        user_id = context.actor.id
        template = PaymentTemplate(
            user_id=user_id,
            name=normalise_template_name(command.name),
            beneficiary=normalise_counterparty(command.beneficiary),
            iban=normalise_iban(command.iban),
            currency=normalise_currency(command.currency),
            reference=normalise_reference(command.reference),
            created_at=self._clock.now(),
            updated_at=self._clock.now(),
        )
        await self._templates.add(template, session=session)
        return CommandResult(
            data=template.public_view(),
            audit=AuditRecord(
                action="payments.template_added",
                entity_type="payment_template",
                entity_id=template.id,
                after=template.public_view(),
            ),
            events=[
                DomainEvent(
                    name="payments.template_added",
                    aggregate_type="payment_template",
                    aggregate_id=template.id,
                    payload=template.public_view(),
                )
            ],
        )

    async def _handle_update_template(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, UpdateTemplate)
        template = await self._load_owned_template(command.template_id, context.actor.id)
        before = template.public_view()
        template.update(
            name=normalise_template_name(command.name),
            beneficiary=normalise_counterparty(command.beneficiary),
            iban=normalise_iban(command.iban),
            currency=normalise_currency(command.currency),
            reference=normalise_reference(command.reference),
            now=self._clock.now(),
        )
        await self._templates.update(template, session=session)
        return CommandResult(
            data=template.public_view(),
            audit=AuditRecord(
                action="payments.template_updated",
                entity_type="payment_template",
                entity_id=template.id,
                before=before,
                after=template.public_view(),
            ),
            events=[
                DomainEvent(
                    name="payments.template_updated",
                    aggregate_type="payment_template",
                    aggregate_id=template.id,
                    payload=template.public_view(),
                )
            ],
        )

    async def _handle_delete_template(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, DeleteTemplate)
        template = await self._load_owned_template(command.template_id, context.actor.id)
        await self._templates.delete(template.id, session=session)
        return CommandResult(
            data={"templateId": template.id, "deleted": True},
            audit=AuditRecord(
                action="payments.template_deleted",
                entity_type="payment_template",
                entity_id=template.id,
                before=template.public_view(),
            ),
            events=[
                DomainEvent(
                    name="payments.template_deleted",
                    aggregate_type="payment_template",
                    aggregate_id=template.id,
                )
            ],
        )

    async def list_templates(self, user_id: str) -> dict[str, Any]:
        found = await self._templates.list_for_user(user_id)
        return {"templates": [item.public_view() for item in found]}

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
        ibans = await self._payments.ibans_by_journal_transaction_ids(
            [row["transactionId"] for row in rows]
        )
        for row in rows:
            row["iban"] = ibans.get(row["transactionId"], "")
        return {
            "transactions": rows,
            "nextCursor": encode_cursor(*next_cursor) if next_cursor else None,
        }

    async def statement_data(
        self,
        user_id: str,
        account_id: str,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> dict[str, Any]:
        account = await self._accounts.get_owned(account_id, user_id)
        movements = await self._ledger.statement_movements(account.id, date_from, date_to)
        opening_balance = (
            0 if date_from is None else await self._ledger.opening_balance(account.id, date_from)
        )
        period_total = sum(row["amount"]["minorUnits"] for row in movements)
        return {
            "account": account.public_view(opening_balance + period_total),
            "dateFrom": date_from.isoformat() if date_from else None,
            "dateTo": date_to.isoformat() if date_to else None,
            "openingBalanceMinor": opening_balance,
            "closingBalanceMinor": opening_balance + period_total,
            "movements": movements,
        }


@lru_cache(maxsize=1)
def get_payments_service() -> PaymentsService:
    service = PaymentsService(
        payments=MongoPaymentRepository(),
        beneficiaries=MongoBeneficiaryRepository(),
        templates=MongoPaymentTemplateRepository(),
        accounts=get_accounts_service(),
        ledger=get_ledger_service(),
        exchange=get_exchange_service(),
        policy=StaticLimitPolicy(settings),
        step_up=DevCodeStepUp(settings),
        payees=InternalPayeeVerifier(),
        hasher=Argon2idHasher(),
        auth=get_auth_service(),
        clock=SystemClock(),
        config=settings,
    )
    service.register(bus)
    return service
