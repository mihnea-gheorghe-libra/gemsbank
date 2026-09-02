from datetime import datetime, timezone

import pytest

from backend.accounts.account import AccountStatus
from backend.admin.service import CloseAccount, FreezeAccount, UnfreezeAccount
from backend.auth.credentials import AuthUser
from backend.helpers.errors import IllegalTransitionError, ValidationError
from backend.tests.admin_fakes import (
    account,
    admin_context,
    build_admin_service,
)


def _customer(status: str = "active") -> AuthUser:
    return AuthUser(
        id="user-1",
        username="anapop",
        email="ana@example.test",
        password_hash="x",
        pin_hash="y",
        status=status,
    )


async def test_freezing_an_account_records_the_reason_and_who_froze_it() -> None:
    held = account()
    service, parts = build_admin_service(accounts=[held])

    result = await service._handle_freeze(
        FreezeAccount(account_id=held.id, reason="Suspected mule account"),
        admin_context(),
        session=None,
    )

    stored = parts["accounts"].accounts[held.id]
    assert stored.status is AccountStatus.FROZEN
    assert stored.status_reason == "Suspected mule account"
    assert stored.status_changed_by == "admin:admin"
    assert result.data["statusReason"] == "Suspected mule account"


async def test_a_frozen_account_cannot_send_but_still_receives() -> None:
    held = account()
    service, parts = build_admin_service(accounts=[held])

    await service._handle_freeze(
        FreezeAccount(account_id=held.id, reason="Suspected mule account"),
        admin_context(),
        session=None,
    )
    frozen = parts["accounts"].accounts[held.id]

    with pytest.raises(IllegalTransitionError):
        frozen.guard_can_send()
    frozen.guard_can_receive()


async def test_freezing_an_account_does_not_lock_the_customer_out_of_signing_in() -> None:
    held = account()
    service, _ = build_admin_service(accounts=[held])

    await service._handle_freeze(
        FreezeAccount(account_id=held.id, reason="Suspected mule account"),
        admin_context(),
        session=None,
    )

    _customer().guard_usable(datetime(2026, 1, 1, tzinfo=timezone.utc))


async def test_an_account_cannot_be_frozen_twice() -> None:
    held = account()
    service, _ = build_admin_service(accounts=[held])
    command = FreezeAccount(account_id=held.id, reason="Suspected mule account")

    await service._handle_freeze(command, admin_context(), session=None)

    with pytest.raises(IllegalTransitionError):
        await service._handle_freeze(command, admin_context(), session=None)


async def test_unfreezing_restores_sending_and_keeps_its_own_reason() -> None:
    held = account()
    service, parts = build_admin_service(accounts=[held])
    await service._handle_freeze(
        FreezeAccount(account_id=held.id, reason="Suspected mule account"),
        admin_context(),
        session=None,
    )

    await service._handle_unfreeze(
        UnfreezeAccount(account_id=held.id, reason="Investigation closed, no findings"),
        admin_context(),
        session=None,
    )

    stored = parts["accounts"].accounts[held.id]
    assert stored.status is AccountStatus.ACTIVE
    assert stored.status_reason == "Investigation closed, no findings"
    stored.guard_can_send()


async def test_an_account_that_is_not_frozen_cannot_be_unfrozen() -> None:
    held = account()
    service, _ = build_admin_service(accounts=[held])

    with pytest.raises(IllegalTransitionError):
        await service._handle_unfreeze(
            UnfreezeAccount(account_id=held.id, reason="Nothing to undo here"),
            admin_context(),
            session=None,
        )


async def test_a_closed_account_cannot_be_frozen() -> None:
    held = account(status=AccountStatus.CLOSED)
    service, _ = build_admin_service(accounts=[held])

    with pytest.raises(IllegalTransitionError):
        await service._handle_freeze(
            FreezeAccount(account_id=held.id, reason="Too late for this one"),
            admin_context(),
            session=None,
        )


async def test_freezing_an_account_needs_a_reason() -> None:
    held = account()
    service, parts = build_admin_service(accounts=[held])

    with pytest.raises(ValidationError):
        await service._handle_freeze(
            FreezeAccount(account_id=held.id, reason="no"),
            admin_context(),
            session=None,
        )
    assert parts["accounts"].accounts[held.id].status is AccountStatus.ACTIVE


async def test_admin_can_close_an_active_account_with_reason_and_audit() -> None:
    held = account()
    service, parts = build_admin_service(accounts=[held])

    result = await service._handle_close(
        CloseAccount(account_id=held.id, reason="Compliance request account termination"),
        admin_context(),
        session=None,
    )

    stored = parts["accounts"].accounts[held.id]
    assert stored.status is AccountStatus.CLOSED
    assert stored.status_reason == "Compliance request account termination"
    assert stored.status_changed_by == "admin:admin"
    assert result.data["statusReason"] == "Compliance request account termination"
    assert result.data["status"] == "closed"
    assert result.audit.action == "admin.account_closed"


async def test_admin_can_close_a_frozen_account() -> None:
    held = account(status=AccountStatus.FROZEN)
    service, parts = build_admin_service(accounts=[held])

    result = await service._handle_close(
        CloseAccount(account_id=held.id, reason="Fraud confirmed, account terminated"),
        admin_context(),
        session=None,
    )

    stored = parts["accounts"].accounts[held.id]
    assert stored.status is AccountStatus.CLOSED
    assert stored.status_reason == "Fraud confirmed, account terminated"
    assert stored.status_changed_by == "admin:admin"
    assert result.data["status"] == "closed"


async def test_a_closed_account_cannot_be_closed_again() -> None:
    held = account(status=AccountStatus.CLOSED)
    service, _ = build_admin_service(accounts=[held])

    with pytest.raises(IllegalTransitionError):
        await service._handle_close(
            CloseAccount(account_id=held.id, reason="Already closed anyway"),
            admin_context(),
            session=None,
        )


async def test_closing_an_account_needs_a_reason() -> None:
    held = account()
    service, parts = build_admin_service(accounts=[held])

    with pytest.raises(ValidationError):
        await service._handle_close(
            CloseAccount(account_id=held.id, reason="no"),
            admin_context(),
            session=None,
        )
    assert parts["accounts"].accounts[held.id].status is AccountStatus.ACTIVE

