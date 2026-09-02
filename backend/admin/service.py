import secrets
from collections.abc import Sequence
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, ClassVar, Protocol

from motor.motor_asyncio import AsyncIOMotorClientSession

from backend.accounts.service import (
    Account,
    AccountsService,
    AccountStatus,
    get_accounts_service,
)
from backend.admin import validation
from backend.admin.adapters import SystemClock
from backend.admin.session import (
    GENERIC_ADMIN_REJECTION,
    AdminIdentity,
    AdminSession,
)
from backend.command_bus import Command, CommandBus, CommandResult, bus
from backend.config import Settings, settings
from backend.credits.service import CreditsService, get_credits_service
from backend.database.records import AuditRecord, DomainEvent
from backend.database.repositories import (
    MongoAdminSessionRepository,
    MongoAuthUserRepository,
)
from backend.helpers.context import Actor, ActorContext
from backend.helpers.crypto import hash_token, new_opaque_token
from backend.helpers.errors import (
    AuthenticationError,
    AuthorizationError,
    IllegalTransitionError,
    NotFoundError,
)
from backend.helpers.paging import decode_cursor, encode_cursor
from backend.ledger.service import LedgerService, get_ledger_service
from backend.products.catalogue import estimate_repayment

__all__ = ["AdminService", "get_admin_service"]


class AdminSessionRepository(Protocol):
    async def add(
        self, record: AdminSession, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...

    async def get_by_token_hash(self, token_hash: str) -> AdminSession | None: ...

    async def revoke(
        self, record: AdminSession, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...


class Customer(Protocol):
    id: str
    username: str
    email: str
    phone: str | None
    full_name: str
    status: str
    created_at: datetime | None
    monthly_income_minor: int | None


class CustomerDirectory(Protocol):
    async def get(self, user_id: str) -> Customer | None: ...

    async def page(
        self, search: str | None, cursor: tuple[datetime, str] | None, limit: int
    ) -> Sequence[Customer]: ...

    async def count(self, search: str | None) -> int: ...

    async def set_monthly_income(
        self, user_id: str, minor: int, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...

    async def set_status(
        self, user_id: str, status: str, session: AsyncIOMotorClientSession | None = None
    ) -> bool: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class AdminSignIn(Command):
    command_name: ClassVar[str] = "admin.sign_in"

    username: str
    password: str


class AdminSignOut(Command):
    command_name: ClassVar[str] = "admin.sign_out"

    session_token: str


class ReverseTransaction(Command):
    command_name: ClassVar[str] = "admin.transaction.reverse"

    transaction_id: str
    reason: str


class FreezeAccount(Command):
    command_name: ClassVar[str] = "admin.account.freeze"

    account_id: str
    reason: str


class UnfreezeAccount(Command):
    command_name: ClassVar[str] = "admin.account.unfreeze"

    account_id: str
    reason: str


class CloseAccount(Command):
    command_name: ClassVar[str] = "admin.account.close"

    account_id: str
    reason: str


class LockUser(Command):
    command_name: ClassVar[str] = "admin.user.lock"

    user_id: str
    reason: str


class UnlockUser(Command):
    command_name: ClassVar[str] = "admin.user.unlock"

    user_id: str
    reason: str


class ApproveCreditApplication(Command):
    command_name: ClassVar[str] = "admin.credit.approve"

    application_id: str
    reason: str


class RejectCreditApplication(Command):
    command_name: ClassVar[str] = "admin.credit.reject"

    application_id: str
    reason: str


def _customer_view(customer: Customer) -> dict[str, Any]:
    return {
        "userId": customer.id,
        "username": customer.username,
        "email": customer.email,
        "phone": customer.phone,
        "fullName": customer.full_name,
        "status": customer.status,
        "createdAt": customer.created_at.isoformat() if customer.created_at else None,
    }


class AdminService:
    def __init__(
        self,
        sessions: AdminSessionRepository,
        customers: CustomerDirectory,
        accounts: AccountsService,
        ledger: LedgerService,
        credits: CreditsService,
        clock: Clock,
        config: Settings,
    ) -> None:
        self._sessions = sessions
        self._customers = customers
        self._accounts = accounts
        self._ledger = ledger
        self._credits = credits
        self._clock = clock
        self._config = config

    def register(self, command_bus: CommandBus) -> None:
        command_bus.register(AdminSignIn, self._handle_sign_in)
        command_bus.register(AdminSignOut, self._handle_sign_out)
        command_bus.register(ReverseTransaction, self._handle_reverse)
        command_bus.register(FreezeAccount, self._handle_freeze)
        command_bus.register(UnfreezeAccount, self._handle_unfreeze)
        command_bus.register(CloseAccount, self._handle_close)
        command_bus.register(LockUser, self._handle_lock_user)
        command_bus.register(UnlockUser, self._handle_unlock_user)
        command_bus.register(ApproveCreditApplication, self._handle_approve)
        command_bus.register(RejectCreditApplication, self._handle_reject)

    def _require_admin(self, actor: Actor) -> str:
        if actor.kind != "admin":
            raise AuthorizationError("This action is for administrators only.")
        return actor.label()

    def _match_credentials(self, username: str, password: str) -> AdminIdentity:
        expected = self._config.admin_password
        if not expected:
            raise AuthenticationError(
                "Administrator sign-in is not configured on this deployment."
            )
        username_ok = secrets.compare_digest(
            username.strip().lower(), self._config.admin_username.strip().lower()
        )
        password_ok = secrets.compare_digest(password, expected)
        if not (username_ok and password_ok):
            raise AuthenticationError(GENERIC_ADMIN_REJECTION)
        return AdminIdentity(
            id=self._config.admin_username, username=self._config.admin_username
        )

    async def resolve_admin(self, token: str) -> AdminIdentity:
        record = await self._sessions.get_by_token_hash(hash_token(token))
        if record is None:
            raise AuthenticationError("Sign in to continue.")
        record.guard_live(self._clock.now())
        return record.identity()

    async def resolve_actor(self, token: str) -> Actor:
        identity = await self.resolve_admin(token)
        return Actor.admin(identity.id)

    async def list_customers(
        self, search: str | None, cursor: str | None, limit: int | None
    ) -> dict[str, Any]:
        term = validation.normalise_search(search)
        page_size = validation.normalise_page_size(limit, self._config.admin_users_page_size)
        found = await self._customers.page(term, decode_cursor(cursor), page_size + 1)
        has_more = len(found) > page_size
        found = found[:page_size]
        last_created_at = found[-1].created_at if found else None
        next_cursor = (
            encode_cursor(last_created_at, found[-1].id)
            if has_more and last_created_at is not None
            else None
        )
        return {
            "users": [_customer_view(customer) for customer in found],
            "total": await self._customers.count(term),
            "nextCursor": next_cursor,
        }

    async def _customer(self, user_id: str) -> Customer:
        customer = await self._customers.get(user_id)
        if customer is None:
            raise NotFoundError("There is no such user.", details={"field": "userId"})
        return customer

    async def _estimate_monthly_income(self, user_id: str) -> int:
        owned = await self._accounts.owned_accounts(user_id)
        account_ids = [account.id for account in owned]
        if not account_ids:
            return 0
        since = self._clock.now() - timedelta(days=validation.INCOME_LOOKBACK_DAYS)
        rows, _ = await self._ledger.movements(
            account_ids, direction="credit", limit=validation.INCOME_SAMPLE_LIMIT
        )
        total: int = sum(
            int(row["amount"]["minorUnits"])
            for row in rows
            if row["category"] == "income"
            and row["amount"]["currency"] == "RON"
            and datetime.fromisoformat(row["postedAt"]) >= since
        )
        return round(total / validation.INCOME_LOOKBACK_MONTHS)

    async def _monthly_income(self, customer: Customer) -> int:
        if customer.monthly_income_minor is not None:
            return customer.monthly_income_minor
        estimate = await self._estimate_monthly_income(customer.id)
        await self._customers.set_monthly_income(customer.id, estimate)
        return estimate

    async def _credit_support(
        self, customer: Customer, view: dict[str, Any]
    ) -> dict[str, Any]:
        monthly_income = await self._monthly_income(customer)

        term_months = view["termMonths"]
        estimated_monthly_payment = None
        if term_months:
            estimated_monthly_payment, _, _ = estimate_repayment(
                view["amount"]["minorUnits"], term_months, view["rateBps"]
            )

        payout = await self._accounts.get_any(view["payoutAccountId"])
        current_balance = await self._ledger.balance_of(payout.id)

        others = [
            other
            for other in await self._credits.list_for_user(customer.id)
            if other["status"] == "approved"
            and other["applicationId"] != view["applicationId"]
        ]

        return {
            "monthlyIncomeMinorUnits": monthly_income,
            "estimatedMonthlyPaymentMinorUnits": estimated_monthly_payment,
            "currentBalanceMinorUnits": current_balance,
            "currentBalanceCurrency": payout.currency,
            "otherActiveCredits": others,
        }

    async def customer_detail(self, user_id: str) -> dict[str, Any]:
        customer = await self._customer(user_id)
        applications = await self._credits.list_for_user(user_id)
        enriched: list[dict[str, Any]] = []
        for view in applications:
            if view["status"] == "review":
                view = view | {"support": await self._credit_support(customer, view)}
            enriched.append(view)
        return {
            "user": _customer_view(customer),
            "accounts": await self._accounts.list_for_user(user_id),
            "creditApplications": enriched,
        }

    async def customer_transactions(
        self,
        user_id: str,
        *,
        direction: str | None = None,
        search: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        await self._customer(user_id)
        owned = await self._accounts.owned_accounts(user_id)
        page_size = validation.normalise_page_size(
            limit, self._config.transactions_page_size
        )
        rows, next_cursor = await self._ledger.movements(
            [account.id for account in owned],
            direction=direction,
            search=validation.normalise_search(search),
            cursor=decode_cursor(cursor),
            limit=page_size,
        )
        labels = {account.id: account.label for account in owned}
        for row in rows:
            row["accountLabel"] = labels.get(row["accountId"], "")
        return {
            "transactions": rows,
            "nextCursor": encode_cursor(*next_cursor) if next_cursor else None,
        }

    async def _party_view(self, account_id: str) -> dict[str, Any]:
        if account_id.startswith("house:"):
            return {
                "accountId": account_id,
                "iban": None,
                "holderName": "GEMS Bank",
                "userId": None,
                "label": account_id,
                "isHouse": True,
            }
        account = await self._accounts.get_optional(account_id)
        if account is None:
            return {
                "accountId": account_id,
                "iban": None,
                "holderName": None,
                "userId": None,
                "label": None,
                "isHouse": False,
            }
        return {
            "accountId": account.id,
            "iban": account.iban,
            "holderName": account.holder_name,
            "userId": account.user_id,
            "label": account.label,
            "isHouse": False,
        }

    async def transaction_detail(self, transaction_id: str) -> dict[str, Any]:
        transaction = await self._ledger.get_transaction(transaction_id)
        reversal = await self._ledger.reversal_of(transaction_id)

        legs: list[dict[str, Any]] = []
        for entry in transaction.entries:
            party = await self._party_view(entry.account_id)
            legs.append(
                party
                | {
                    "amountMinorUnits": entry.amount,
                    "direction": "credit" if entry.amount > 0 else "debit",
                }
            )
        payer = next((leg for leg in legs if leg["amountMinorUnits"] < 0), None)
        payee = next((leg for leg in legs if leg["amountMinorUnits"] > 0), None)
        amount_minor = max(abs(entry.amount) for entry in transaction.entries)

        return {
            "transactionId": transaction.id,
            "kind": transaction.kind.value,
            "postedAt": transaction.posted_at.isoformat(),
            "currency": transaction.currency,
            "amountMinorUnits": amount_minor,
            "reference": transaction.reference,
            "counterparty": transaction.counterparty,
            "category": transaction.category,
            "correlationId": transaction.correlation_id,
            "actor": transaction.actor,
            "reverses": transaction.reverses,
            "reason": transaction.reason,
            "reversalTransactionId": reversal.id if reversal is not None else None,
            "payer": payer,
            "payee": payee,
            "legs": legs,
        }

    async def list_applications(
        self, status: str | None, cursor: str | None, limit: int | None
    ) -> dict[str, Any]:
        wanted = validation.normalise_application_status(status)
        page_size = validation.normalise_page_size(limit, self._config.admin_users_page_size)
        found, next_cursor = await self._credits.page(
            wanted, decode_cursor(cursor), page_size
        )

        customers: dict[str, Customer | None] = {}
        for application in found:
            if application.user_id not in customers:
                customers[application.user_id] = await self._customers.get(
                    application.user_id
                )

        applications_view: list[dict[str, Any]] = []
        for application in found:
            customer = customers[application.user_id]
            view = application.public_view() | {
                "userId": application.user_id,
                "applicant": _customer_view(customer) if customer is not None else None,
            }
            if application.status == "review" and customer is not None:
                view["support"] = await self._credit_support(customer, view)
            applications_view.append(view)

        return {
            "applications": applications_view,
            "total": await self._credits.count(wanted),
            "nextCursor": encode_cursor(*next_cursor) if next_cursor else None,
        }

    async def _handle_sign_in(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, AdminSignIn)
        identity = self._match_credentials(command.username, command.password)

        token = new_opaque_token()
        now = self._clock.now()
        record = AdminSession(
            admin_id=identity.id,
            username=identity.username,
            token_hash=hash_token(token),
            issued_at=now,
            expires_at=now + timedelta(seconds=self._config.admin_session_ttl_seconds),
            ip_address=context.ip,
            user_agent=context.user_agent,
        )
        await self._sessions.add(record, session=session)

        return CommandResult(
            data=identity.public_view(),
            sensitive={"sessionToken": token} | record.public_view(),
            audit=AuditRecord(
                action="admin.signed_in",
                entity_type="adminSession",
                entity_id=record.id,
                after={"adminId": identity.id},
            ),
            events=[
                DomainEvent(
                    name="admin.signed_in",
                    aggregate_type="adminSession",
                    aggregate_id=record.id,
                )
            ],
        )

    async def _handle_sign_out(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, AdminSignOut)
        self._require_admin(context.actor)
        record = await self._sessions.get_by_token_hash(hash_token(command.session_token))
        if record is None:
            raise NotFoundError("That session is already gone.")
        record.revoke(self._clock.now())
        await self._sessions.revoke(record, session=session)

        return CommandResult(
            data={"signedOut": True},
            audit=AuditRecord(
                action="admin.signed_out",
                entity_type="adminSession",
                entity_id=record.id,
                after={"adminId": record.admin_id},
            ),
            events=[
                DomainEvent(
                    name="admin.signed_out",
                    aggregate_type="adminSession",
                    aggregate_id=record.id,
                )
            ],
        )

    async def _handle_reverse(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, ReverseTransaction)
        actor_label = self._require_admin(context.actor)
        reason = validation.normalise_reason(command.reason)

        original = await self._ledger.get_transaction(command.transaction_id)
        reversal = await self._ledger.reverse(
            transaction=original,
            reason=reason,
            correlation_id=context.correlation_id,
            actor=actor_label,
            session=session,
        )

        view = {
            "reversalTransactionId": reversal.id,
            "reversedTransactionId": original.id,
            "reason": reason,
            "postedAt": reversal.posted_at.isoformat(),
            "currency": reversal.currency,
            "entries": [
                {"accountId": entry.account_id, "minorUnits": entry.amount}
                for entry in reversal.entries
            ],
        }
        return CommandResult(
            data=view,
            audit=AuditRecord(
                action="admin.transaction_reversed",
                entity_type="journalTransaction",
                entity_id=original.id,
                before={"transactionId": original.id, "reference": original.reference},
                after=view,
            ),
            events=[
                DomainEvent(
                    name="admin.transaction_reversed",
                    aggregate_type="journalTransaction",
                    aggregate_id=reversal.id,
                    payload={"reverses": original.id, "reason": reason},
                )
            ],
        )

    async def _change_account_status(
        self,
        account_id: str,
        reason: str,
        status: AccountStatus,
        action: str,
        context: ActorContext,
        session: AsyncIOMotorClientSession,
    ) -> CommandResult:
        actor_label = self._require_admin(context.actor)
        account: Account = await self._accounts.get_any(account_id)
        if status is AccountStatus.FROZEN:
            account.guard_can_freeze()
        elif status is AccountStatus.ACTIVE:
            account.guard_can_unfreeze()
        elif status is AccountStatus.CLOSED:
            account.guard_can_close()

        before = await self._accounts.view_of(account)
        updated = await self._accounts.set_status_with_reason(
            account, status, reason, actor_label, session=session
        )
        after = await self._accounts.view_of(updated)

        return CommandResult(
            data=after,
            audit=AuditRecord(
                action=action,
                entity_type="account",
                entity_id=account.id,
                before=before,
                after=after | {"reason": reason},
            ),
            events=[
                DomainEvent(
                    name=action,
                    aggregate_type="account",
                    aggregate_id=account.id,
                    payload={"userId": account.user_id, "reason": reason},
                )
            ],
        )

    async def _handle_freeze(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, FreezeAccount)
        return await self._change_account_status(
            command.account_id,
            validation.normalise_reason(command.reason),
            AccountStatus.FROZEN,
            "admin.account_frozen",
            context,
            session,
        )

    async def _handle_unfreeze(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, UnfreezeAccount)
        return await self._change_account_status(
            command.account_id,
            validation.normalise_reason(command.reason),
            AccountStatus.ACTIVE,
            "admin.account_unfrozen",
            context,
            session,
        )

    async def _handle_close(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, CloseAccount)
        return await self._change_account_status(
            command.account_id,
            validation.normalise_reason(command.reason),
            AccountStatus.CLOSED,
            "admin.account_closed",
            context,
            session,
        )

    async def _change_user_status(
        self,
        user_id: str,
        reason: str,
        status: str,
        action: str,
        context: ActorContext,
        session: AsyncIOMotorClientSession,
    ) -> CommandResult:
        actor_label = self._require_admin(context.actor)
        customer = await self._customer(user_id)
        if status == "locked":
            if customer.status == "locked":
                raise IllegalTransitionError(
                    "That user is already locked.",
                    details={"field": "userId", "status": customer.status},
                )
        elif status == "active":
            if customer.status != "locked":
                raise IllegalTransitionError(
                    "That user is not locked.",
                    details={"field": "userId", "status": customer.status},
                )

        before = _customer_view(customer)
        await self._customers.set_status(customer.id, status, session=session)
        after = before | {"status": status}

        return CommandResult(
            data=after,
            audit=AuditRecord(
                action=action,
                entity_type="user",
                entity_id=customer.id,
                before=before,
                after=after | {"reason": reason},
            ),
            events=[
                DomainEvent(
                    name=action,
                    aggregate_type="user",
                    aggregate_id=customer.id,
                    payload={"userId": customer.id, "reason": reason},
                )
            ],
        )

    async def _handle_lock_user(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, LockUser)
        return await self._change_user_status(
            command.user_id,
            validation.normalise_reason(command.reason),
            "locked",
            "admin.user_locked",
            context,
            session,
        )

    async def _handle_unlock_user(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, UnlockUser)
        return await self._change_user_status(
            command.user_id,
            validation.normalise_reason(command.reason),
            "active",
            "admin.user_unlocked",
            context,
            session,
        )

    async def _decide_application(
        self,
        application_id: str,
        reason: str,
        status: str,
        action: str,
        context: ActorContext,
        session: AsyncIOMotorClientSession,
    ) -> CommandResult:
        actor_label = self._require_admin(context.actor)
        application = await self._credits.get(application_id)
        before = application.public_view()
        decided = await self._credits.decide(
            application,
            "approved" if status == "approved" else "rejected",
            reason,
            actor_label,
            session=session,
        )
        after = decided.public_view()

        return CommandResult(
            data=after,
            audit=AuditRecord(
                action=action,
                entity_type="creditApplication",
                entity_id=application.id,
                before=before,
                after=after,
            ),
            events=[
                DomainEvent(
                    name=action,
                    aggregate_type="creditApplication",
                    aggregate_id=application.id,
                    payload={"userId": application.user_id, "reason": reason},
                )
            ],
        )

    async def _handle_approve(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, ApproveCreditApplication)
        return await self._decide_application(
            command.application_id,
            validation.normalise_reason(command.reason),
            "approved",
            "admin.credit_approved",
            context,
            session,
        )

    async def _handle_reject(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, RejectCreditApplication)
        return await self._decide_application(
            command.application_id,
            validation.normalise_reason(command.reason),
            "rejected",
            "admin.credit_rejected",
            context,
            session,
        )


@lru_cache(maxsize=1)
def get_admin_service() -> AdminService:
    service = AdminService(
        sessions=MongoAdminSessionRepository(),
        customers=MongoAuthUserRepository(),
        accounts=get_accounts_service(),
        ledger=get_ledger_service(),
        credits=get_credits_service(),
        clock=SystemClock(),
        config=settings,
    )
    service.register(bus)
    return service
