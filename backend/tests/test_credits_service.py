from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from backend.accounts.account import Account, AccountKind
from backend.accounts.service import AccountsService
from backend.credits.service import (
    CreditsService,
    SubmitCreditApplication,
    WithdrawCreditApplication,
)
from backend.helpers.context import Actor, ActorContext
from backend.helpers.errors import (
    IllegalTransitionError,
    NotFoundError,
    ValidationError,
)
from backend.ledger.service import LedgerService


class _FakeAccountRepository:
    def __init__(self, accounts: list[Account]) -> None:
        self._accounts = {account.id: account for account in accounts}

    async def add(self, account, session=None) -> None:
        self._accounts[account.id] = account

    async def get(self, account_id: str):
        return self._accounts.get(account_id)

    async def get_by_iban(self, iban: str):
        return next((a for a in self._accounts.values() if a.iban == iban), None)

    async def list_for_user(self, user_id: str) -> list[Account]:
        return [
            a for a in self._accounts.values()
            if a.user_id == user_id or user_id in a.owner_ids
        ]

    async def add_owner(self, account_id: str, user_id: str, session=None) -> None:
        account = self._accounts.get(account_id)
        if account is not None and user_id not in account.owner_ids:
            self._accounts[account_id] = account.model_copy(
                update={"owner_ids": [*account.owner_ids, user_id]}
            )

    async def set_status(self, account_id: str, status, session=None) -> bool:
        return True


class _FakeJournalRepository:
    async def append(self, transaction, session=None) -> None:
        return None

    async def balances_for(self, account_ids: list[str]) -> dict[str, int]:
        return {account_id: 0 for account_id in account_ids}

    async def page_for(self, *args, **kwargs):
        raise NotImplementedError

    async def debited_since(self, account_ids, since) -> int:
        raise NotImplementedError

    async def count_for(self, account_ids) -> int:
        return 0


class _FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 1, 1, tzinfo=timezone.utc)

    def today(self) -> date:
        return date(2026, 1, 1)


class _FakeUserDirectory:
    async def get(self, user_id: str):
        return SimpleNamespace(display_name="Test User")


class _FakeApplicationRepository:
    def __init__(self) -> None:
        self._applications: dict[str, object] = {}

    async def add(self, application, session=None) -> None:
        self._applications[application.id] = application

    async def get(self, application_id: str):
        return self._applications.get(application_id)

    async def list_for_user(self, user_id: str):
        return [a for a in self._applications.values() if a.user_id == user_id]

    async def set_status(self, application_id: str, user_id: str, status: str, session=None) -> bool:
        application = self._applications.get(application_id)
        if application is None or application.user_id != user_id or application.status != "review":
            return False
        self._applications[application_id] = application.model_copy(update={"status": status})
        return True


def _account(user_id: str = "user-1") -> Account:
    return Account(
        user_id=user_id,
        iban="RO00TESTBANK0000000001",
        holder_name="Test User",
        currency="RON",
        kind=AccountKind.CURRENT,
        label="Current",
    )


def _context(user_id: str = "user-1") -> ActorContext:
    return ActorContext(actor=Actor(kind="user", id=user_id), correlation_id="corr-1")


def _build_service(account: Account):
    accounts_service = AccountsService(
        accounts=_FakeAccountRepository([account]),
        ledger=LedgerService(journal=_FakeJournalRepository(), clock=_FixedClock()),
        users=_FakeUserDirectory(),
        clock=_FixedClock(),
    )
    application_repo = _FakeApplicationRepository()
    service = CreditsService(applications=application_repo, accounts=accounts_service)
    return service, application_repo


async def test_submit_application_looks_up_rate_from_the_catalogue() -> None:
    account = _account()
    service, repo = _build_service(account)
    command = SubmitCreditApplication(
        product_id="personal",
        amount_minor=5_000_000,
        term_months=24,
        purpose="Renovation",
        payout_account_id=account.id,
    )

    result = await service._handle_submit(command, _context(), session=None)

    assert result.data["status"] == "review"
    assert result.data["rateBps"] == 830
    stored = await repo.list_for_user("user-1")
    assert len(stored) == 1


async def test_submit_application_rejects_amount_over_product_maximum() -> None:
    account = _account()
    service, _ = _build_service(account)
    command = SubmitCreditApplication(
        product_id="line",
        amount_minor=3_000_000,
        term_months=None,
        purpose="",
        payout_account_id=account.id,
    )

    with pytest.raises(ValidationError):
        await service._handle_submit(command, _context(), session=None)


async def test_submit_application_rejects_an_unlisted_term() -> None:
    account = _account()
    service, _ = _build_service(account)
    command = SubmitCreditApplication(
        product_id="personal",
        amount_minor=1_000_000,
        term_months=13,
        purpose="",
        payout_account_id=account.id,
    )

    with pytest.raises(ValidationError):
        await service._handle_submit(command, _context(), session=None)


async def test_withdraw_application_transitions_status_and_is_final() -> None:
    account = _account()
    service, _repo = _build_service(account)
    created = await service._handle_submit(
        SubmitCreditApplication(
            product_id="line",
            amount_minor=100_000,
            term_months=None,
            purpose="",
            payout_account_id=account.id,
        ),
        _context(),
        session=None,
    )
    application_id = created.data["applicationId"]

    result = await service._handle_withdraw(
        WithdrawCreditApplication(application_id=application_id), _context(), session=None
    )
    assert result.data["status"] == "withdrawn"

    with pytest.raises(IllegalTransitionError):
        await service._handle_withdraw(
            WithdrawCreditApplication(application_id=application_id), _context(), session=None
        )


async def test_withdraw_someone_elses_application_is_rejected() -> None:
    account = _account()
    service, _ = _build_service(account)
    created = await service._handle_submit(
        SubmitCreditApplication(
            product_id="line",
            amount_minor=100_000,
            term_months=None,
            purpose="",
            payout_account_id=account.id,
        ),
        _context(),
        session=None,
    )
    application_id = created.data["applicationId"]

    with pytest.raises(NotFoundError):
        await service._handle_withdraw(
            WithdrawCreditApplication(application_id=application_id),
            _context(user_id="someone-else"),
            session=None,
        )
