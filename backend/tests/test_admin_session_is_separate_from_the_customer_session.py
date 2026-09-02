import pytest

from backend.admin.service import (
    AdminSignIn,
    AdminSignOut,
    CloseAccount,
    FreezeAccount,
    LockUser,
    UnlockUser,
)
from backend.config import settings
from backend.helpers.crypto import hash_token
from backend.helpers.errors import (
    AuthenticationError,
    AuthorizationError,
    ValidationError,
)
from backend.onboarding.validation import normalise_username
from backend.tests.admin_fakes import (
    ADMIN_PASSWORD,
    FakeCustomer,
    account,
    admin_context,
    build_admin_service,
    customer_context,
)


async def _sign_in(service) -> str:
    result = await service._handle_sign_in(
        AdminSignIn(username="admin", password=ADMIN_PASSWORD),
        admin_context(),
        session=None,
    )
    return result.sensitive["sessionToken"]


async def test_admin_sign_in_mints_a_token_in_its_own_store() -> None:
    service, parts = build_admin_service()

    token = await _sign_in(service)

    assert parts["sessions"].records[hash_token(token)].admin_id == "admin"
    assert (await service.resolve_actor(token)).kind == "admin"


async def test_admin_sign_in_never_touches_the_customer_pin_flow() -> None:
    service, parts = build_admin_service(
        customers=[FakeCustomer("user-1", "admin")]
    )

    with pytest.raises(AuthenticationError):
        await service._handle_sign_in(
            AdminSignIn(username="admin", password="123456"),
            admin_context(),
            session=None,
        )
    assert parts["sessions"].records == {}


async def test_an_unknown_token_is_not_an_admin() -> None:
    service, _ = build_admin_service()

    with pytest.raises(AuthenticationError):
        await service.resolve_actor("not-a-token")


async def test_an_expired_admin_session_stops_authorising() -> None:
    service, parts = build_admin_service()
    token = await _sign_in(service)
    record = parts["sessions"].records[hash_token(token)]
    parts["sessions"].records[hash_token(token)] = record.model_copy(
        update={"expires_at": parts["clock"].now()}
    )

    with pytest.raises(AuthenticationError):
        await service.resolve_actor(token)


async def test_a_revoked_admin_session_stops_authorising() -> None:
    service, _parts = build_admin_service()
    token = await _sign_in(service)

    await service._handle_sign_out(
        AdminSignOut(session_token=token), admin_context(), session=None
    )

    with pytest.raises(AuthenticationError):
        await service.resolve_actor(token)


async def test_a_customer_actor_is_refused_by_every_admin_command() -> None:
    held = account()
    service, _parts = build_admin_service(accounts=[held])

    with pytest.raises(AuthorizationError):
        await service._handle_freeze(
            FreezeAccount(account_id=held.id, reason="Trying it on"),
            customer_context(),
            session=None,
        )

    with pytest.raises(AuthorizationError):
        await service._handle_close(
            CloseAccount(account_id=held.id, reason="Trying to close"),
            customer_context(),
            session=None,
        )

    with pytest.raises(AuthorizationError):
        await service._handle_lock_user(
            LockUser(user_id="user-1", reason="Trying to lock"),
            customer_context(),
            session=None,
        )

    with pytest.raises(AuthorizationError):
        await service._handle_unlock_user(
            UnlockUser(user_id="user-1", reason="Trying to unlock"),
            customer_context(),
            session=None,
        )


async def test_the_admin_username_cannot_be_registered_as_a_customer() -> None:
    with pytest.raises(ValidationError):
        normalise_username(settings.admin_username)
    with pytest.raises(ValidationError):
        normalise_username("  " + settings.admin_username.upper() + " ")


async def test_the_demo_admin_password_is_what_the_sign_in_form_accepts() -> None:
    service, parts = build_admin_service()

    result = await service._handle_sign_in(
        AdminSignIn(username=settings.admin_username, password="000000"),
        admin_context(),
        session=None,
    )

    assert result.data["role"] == "admin"
    assert parts["sessions"].records[hash_token(result.sensitive["sessionToken"])]
