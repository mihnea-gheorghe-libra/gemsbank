from datetime import datetime, timezone
from typing import Any

from backend.accounts.account import Account, AccountKind, AccountStatus
from backend.accounts.service import AccountsService
from backend.admin.service import AdminService
from backend.admin.session import AdminSession
from backend.config import settings
from backend.credits.application import CreditApplication
from backend.credits.service import CreditsService
from backend.helpers.context import Actor, ActorContext
from backend.ledger.journal import JournalTransaction
from backend.ledger.service import LedgerService

ADMIN_PASSWORD = "000000"


class FixedClock:
    def __init__(self, moment: datetime | None = None) -> None:
        self._moment = moment or datetime(2026, 1, 1, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._moment


class FakeJournalRepository:
    def __init__(self) -> None:
        self.transactions: list[JournalTransaction] = []

    async def append(self, transaction: JournalTransaction, session: Any = None) -> None:
        if transaction.reverses is not None and any(
            existing.reverses == transaction.reverses for existing in self.transactions
        ):
            raise AssertionError("the unique index would have refused this insert")
        self.transactions.append(transaction)

    async def get(self, transaction_id: str) -> JournalTransaction | None:
        return next((t for t in self.transactions if t.id == transaction_id), None)

    async def reversal_of(self, transaction_id: str) -> JournalTransaction | None:
        return next((t for t in self.transactions if t.reverses == transaction_id), None)

    async def balances_for(self, account_ids: list[str]) -> dict[str, int]:
        balances = {account_id: 0 for account_id in account_ids}
        for transaction in self.transactions:
            for entry in transaction.entries:
                if entry.account_id in balances:
                    balances[entry.account_id] += entry.amount
        return balances

    async def page_for(
        self,
        account_ids: list[str],
        direction: str | None,
        search: str | None,
        cursor: tuple[datetime, str] | None,
        limit: int,
    ) -> list[JournalTransaction]:
        owned = set(account_ids)
        found = [
            transaction
            for transaction in self.transactions
            if any(entry.account_id in owned for entry in transaction.entries)
        ]
        found.sort(key=lambda t: (t.posted_at, t.id), reverse=True)
        return found[:limit]

    async def count_for(self, account_ids: list[str]) -> int:
        return len(await self.page_for(account_ids, None, None, None, 10_000))

    async def debited_since(self, account_ids: list[str], since: datetime) -> int:
        raise NotImplementedError


class FakeAccountRepository:
    def __init__(self, accounts: list[Account] | None = None) -> None:
        self.accounts = {account.id: account for account in accounts or []}

    async def add(self, account: Account, session: Any = None) -> None:
        self.accounts[account.id] = account

    async def get(self, account_id: str) -> Account | None:
        return self.accounts.get(account_id)

    async def get_by_iban(self, iban: str) -> Account | None:
        return next((a for a in self.accounts.values() if a.iban == iban), None)

    async def list_for_user(self, user_id: str) -> list[Account]:
        return [
            a for a in self.accounts.values()
            if a.user_id == user_id or user_id in a.owner_ids
        ]

    async def add_owner(self, account_id: str, user_id: str, session: Any = None) -> None:
        account = self.accounts.get(account_id)
        if account is not None and user_id not in account.owner_ids:
            self.accounts[account_id] = account.model_copy(
                update={"owner_ids": [*account.owner_ids, user_id]}
            )

    async def set_status(
        self,
        account_id: str,
        status: AccountStatus,
        session: Any = None,
        reason: str | None = None,
        changed_at: datetime | None = None,
        changed_by: str | None = None,
    ) -> bool:
        account = self.accounts.get(account_id)
        if account is None:
            return False
        self.accounts[account_id] = account.model_copy(
            update={
                "status": status,
                "status_reason": reason,
                "status_changed_at": changed_at,
                "status_changed_by": changed_by,
            }
        )
        return True


class FakeApplicationRepository:
    def __init__(self) -> None:
        self.applications: dict[str, CreditApplication] = {}

    async def add(self, application: CreditApplication, session: Any = None) -> None:
        self.applications[application.id] = application

    async def get(self, application_id: str) -> CreditApplication | None:
        return self.applications.get(application_id)

    async def list_for_user(self, user_id: str) -> list[CreditApplication]:
        return [a for a in self.applications.values() if a.user_id == user_id]

    async def page(
        self,
        status: str | None,
        cursor: tuple[datetime, str] | None,
        limit: int,
    ) -> list[CreditApplication]:
        found = [
            a for a in self.applications.values() if status is None or a.status == status
        ]
        found.sort(key=lambda a: (a.submitted_at, a.id), reverse=True)
        return found[:limit]

    async def count(self, status: str | None) -> int:
        return len(await self.page(status, None, 10_000))

    async def set_status(
        self, application_id: str, user_id: str, status: str, session: Any = None
    ) -> bool:
        application = self.applications.get(application_id)
        if application is None or application.user_id != user_id:
            return False
        if application.status != "review":
            return False
        self.applications[application_id] = application.model_copy(
            update={"status": status}
        )
        return True

    async def decide(
        self,
        application_id: str,
        status: str,
        reason: str,
        decided_at: datetime,
        decided_by: str,
        session: Any = None,
    ) -> bool:
        application = self.applications.get(application_id)
        if application is None or application.status != "review":
            return False
        self.applications[application_id] = application.model_copy(
            update={
                "status": status,
                "decision_reason": reason,
                "decided_at": decided_at,
                "decided_by": decided_by,
            }
        )
        return True


class FakeAdminSessionRepository:
    def __init__(self) -> None:
        self.records: dict[str, AdminSession] = {}

    async def add(self, record: AdminSession, session: Any = None) -> None:
        self.records[record.token_hash] = record

    async def get_by_token_hash(self, token_hash: str) -> AdminSession | None:
        return self.records.get(token_hash)

    async def revoke(self, record: AdminSession, session: Any = None) -> None:
        self.records[record.token_hash] = record


class FakeCustomer:
    def __init__(
        self, user_id: str, username: str, monthly_income_minor: int | None = None
    ) -> None:
        self.id = user_id
        self.username = username
        self.email = f"{username}@example.test"
        self.phone = "+40700000000"
        self.full_name = username.replace("-", " ").title()
        self.status = "active"
        self.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
        self.display_name = self.full_name
        self.monthly_income_minor = monthly_income_minor


class FakeCustomerDirectory:
    def __init__(self, customers: list[FakeCustomer] | None = None) -> None:
        self.customers = {customer.id: customer for customer in customers or []}

    async def get(self, user_id: str) -> FakeCustomer | None:
        return self.customers.get(user_id)

    async def set_monthly_income(
        self, user_id: str, minor: int, session: Any = None
    ) -> None:
        customer = self.customers.get(user_id)
        if customer is not None:
            customer.monthly_income_minor = minor

    async def set_status(
        self, user_id: str, status: str, session: Any = None
    ) -> bool:
        customer = self.customers.get(user_id)
        if customer is not None:
            customer.status = status
            return True
        return False

    async def page(
        self, search: str | None, cursor: tuple[datetime, str] | None, limit: int
    ) -> list[FakeCustomer]:
        found = [
            customer
            for customer in self.customers.values()
            if search is None or search.lower() in customer.username.lower()
        ]
        found.sort(key=lambda c: (c.created_at, c.id), reverse=True)
        if cursor is not None:
            created_at, user_id = cursor
            found = [
                c for c in found if (c.created_at, c.id) < (created_at, user_id)
            ]
        return found[:limit]

    async def count(self, search: str | None) -> int:
        return len(await self.page(search, None, 10_000))


def account(
    user_id: str = "user-1",
    iban: str = "RO00TESTBANK0000000001",
    kind: AccountKind = AccountKind.CURRENT,
    status: AccountStatus = AccountStatus.ACTIVE,
) -> Account:
    return Account(
        user_id=user_id,
        iban=iban,
        holder_name="Test User",
        currency="RON",
        kind=kind,
        label="Cont curent",
        status=status,
    )


def admin_context(admin_id: str = "admin") -> ActorContext:
    return ActorContext(actor=Actor.admin(admin_id), correlation_id="corr-admin")


def customer_context(user_id: str = "user-1") -> ActorContext:
    return ActorContext(actor=Actor.user(user_id), correlation_id="corr-user")


def build_admin_service(
    accounts: list[Account] | None = None,
    customers: list[FakeCustomer] | None = None,
) -> tuple[AdminService, dict[str, Any]]:
    clock = FixedClock()
    journal_repo = FakeJournalRepository()
    account_repo = FakeAccountRepository(accounts)
    application_repo = FakeApplicationRepository()
    session_repo = FakeAdminSessionRepository()
    directory = FakeCustomerDirectory(customers)

    ledger = LedgerService(journal=journal_repo, clock=clock)
    accounts_service = AccountsService(
        accounts=account_repo, ledger=ledger, users=directory, clock=clock
    )
    credits_service = CreditsService(
        applications=application_repo, accounts=accounts_service
    )
    service = AdminService(
        sessions=session_repo,
        customers=directory,
        accounts=accounts_service,
        ledger=ledger,
        credits=credits_service,
        clock=clock,
        config=settings,
    )
    parts = {
        "journal": journal_repo,
        "accounts": account_repo,
        "applications": application_repo,
        "sessions": session_repo,
        "customers": directory,
        "ledger": ledger,
        "credits": credits_service,
        "clock": clock,
    }
    return service, parts
