import pytest

from backend.admin.service import LockUser, UnlockUser
from backend.helpers.errors import IllegalTransitionError, NotFoundError, ValidationError
from backend.tests.admin_fakes import (
    FakeCustomer,
    account,
    admin_context,
    build_admin_service,
)


def _directory():
    customers = [FakeCustomer(f"user-{n}", f"customer{n}") for n in range(1, 6)]
    for index, customer in enumerate(customers):
        customer.created_at = customer.created_at.replace(day=index + 1)
    return build_admin_service(customers=customers)


async def test_the_user_list_pages_with_a_cursor_and_reports_the_total() -> None:
    service, _ = _directory()

    first = await service.list_customers(None, None, 2)

    assert len(first["users"]) == 2
    assert first["total"] == 5
    assert first["nextCursor"] is not None

    second = await service.list_customers(None, first["nextCursor"], 2)

    assert len(second["users"]) == 2
    assert {u["userId"] for u in first["users"]} & {
        u["userId"] for u in second["users"]
    } == set()


async def test_the_last_page_hands_back_no_cursor() -> None:
    service, _ = _directory()

    page = await service.list_customers(None, None, 50)

    assert len(page["users"]) == 5
    assert page["nextCursor"] is None


async def test_search_narrows_the_user_list_and_the_total() -> None:
    service, _ = _directory()

    found = await service.list_customers("customer3", None, None)

    assert [u["username"] for u in found["users"]] == ["customer3"]
    assert found["total"] == 1


async def test_a_cursor_we_did_not_issue_is_refused() -> None:
    service, _ = _directory()

    with pytest.raises(ValidationError):
        await service.list_customers(None, "not-a-cursor", None)


async def test_a_user_detail_shows_accounts_and_applications_but_no_secrets() -> None:
    held = account(user_id="user-1")
    service, _ = build_admin_service(
        accounts=[held], customers=[FakeCustomer("user-1", "anapop")]
    )

    detail = await service.customer_detail("user-1")

    assert detail["user"]["username"] == "anapop"
    assert [a["accountId"] for a in detail["accounts"]] == [held.id]
    assert detail["creditApplications"] == []
    assert set(detail["user"]) == {
        "userId",
        "username",
        "email",
        "phone",
        "fullName",
        "status",
        "createdAt",
    }


async def test_an_unknown_user_is_a_not_found() -> None:
    service, _ = build_admin_service()

    with pytest.raises(NotFoundError):
        await service.customer_detail("user-404")


async def test_user_transactions_are_read_from_the_journal_and_labelled() -> None:
    held = account(user_id="user-1")
    other = account(user_id="user-1", iban="RO00TESTBANK0000000002")
    service, parts = build_admin_service(
        accounts=[held, other], customers=[FakeCustomer("user-1", "anapop")]
    )
    await parts["ledger"].transfer(
        source_account_id=held.id,
        target_account_id=other.id,
        amount_minor=50_00,
        currency="RON",
        reference="Economii",
        counterparty="Ana Pop",
        category="transfer",
        correlation_id="corr-1",
        actor="user:user-1",
    )

    page = await service.customer_transactions("user-1")

    assert len(page["transactions"]) == 2
    assert {row["direction"] for row in page["transactions"]} == {"debit", "credit"}
    assert all(row["accountLabel"] == "Cont curent" for row in page["transactions"])


async def test_admin_can_lock_a_user_with_reason_and_audit() -> None:
    customer = FakeCustomer("user-1", "anapop")
    service, parts = build_admin_service(customers=[customer])

    result = await service._handle_lock_user(
        LockUser(user_id="user-1", reason="Suspicious KYC documents"),
        admin_context(),
        session=None,
    )

    stored = parts["customers"].customers["user-1"]
    assert stored.status == "locked"
    assert result.data["status"] == "locked"
    assert result.audit.action == "admin.user_locked"


async def test_admin_can_unlock_a_user() -> None:
    customer = FakeCustomer("user-1", "anapop")
    customer.status = "locked"
    service, parts = build_admin_service(customers=[customer])

    result = await service._handle_unlock_user(
        UnlockUser(user_id="user-1", reason="KYC documents verified successfully"),
        admin_context(),
        session=None,
    )

    stored = parts["customers"].customers["user-1"]
    assert stored.status == "active"
    assert result.data["status"] == "active"
    assert result.audit.action == "admin.user_unlocked"


async def test_locking_an_already_locked_user_fails() -> None:
    customer = FakeCustomer("user-1", "anapop")
    customer.status = "locked"
    service, _ = build_admin_service(customers=[customer])

    with pytest.raises(IllegalTransitionError):
        await service._handle_lock_user(
            LockUser(user_id="user-1", reason="Already locked user"),
            admin_context(),
            session=None,
        )


async def test_unlocking_an_active_user_fails() -> None:
    customer = FakeCustomer("user-1", "anapop")
    customer.status = "active"
    service, _ = build_admin_service(customers=[customer])

    with pytest.raises(IllegalTransitionError):
        await service._handle_unlock_user(
            UnlockUser(user_id="user-1", reason="Not locked anyway"),
            admin_context(),
            session=None,
        )


async def test_locking_a_user_needs_a_reason() -> None:
    customer = FakeCustomer("user-1", "anapop")
    service, parts = build_admin_service(customers=[customer])

    with pytest.raises(ValidationError):
        await service._handle_lock_user(
            LockUser(user_id="user-1", reason="no"),
            admin_context(),
            session=None,
        )
    assert parts["customers"].customers["user-1"].status == "active"


async def test_locking_nonexistent_user_raises_not_found() -> None:
    service, _ = build_admin_service()

    with pytest.raises(NotFoundError):
        await service._handle_lock_user(
            LockUser(user_id="user-nonexistent", reason="Lock non-existent"),
            admin_context(),
            session=None,
        )

