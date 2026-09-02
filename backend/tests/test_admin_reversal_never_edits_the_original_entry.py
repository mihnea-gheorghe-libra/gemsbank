import pytest

from backend.admin.service import ReverseTransaction
from backend.helpers.errors import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from backend.ledger.journal import TransactionKind
from backend.tests.admin_fakes import (
    account,
    admin_context,
    build_admin_service,
    customer_context,
)


async def _posted_transfer(service_parts):
    source, target = account(), account(iban="RO00TESTBANK0000000002")
    parts = service_parts
    return await parts["ledger"].transfer(
        source_account_id=source.id,
        target_account_id=target.id,
        amount_minor=125_00,
        currency="RON",
        reference="Chirie",
        counterparty="Ana Pop",
        category="transfer",
        correlation_id="corr-original",
        actor="user:user-1",
    )


async def test_reversal_adds_a_mirrored_entry_and_leaves_the_original_untouched() -> None:
    service, parts = build_admin_service()
    original = await _posted_transfer(parts)
    snapshot = original.model_dump()

    result = await service._handle_reverse(
        ReverseTransaction(transaction_id=original.id, reason="Fraud reported by holder"),
        admin_context(),
        session=None,
    )

    stored = parts["journal"].transactions
    assert len(stored) == 2
    assert stored[0].model_dump() == snapshot

    reversal = stored[1]
    assert reversal.kind is TransactionKind.REVERSAL
    assert reversal.reverses == original.id
    assert reversal.reason == "Fraud reported by holder"
    assert sum(entry.amount for entry in reversal.entries) == 0
    assert [entry.amount for entry in reversal.entries] == [
        -entry.amount for entry in original.entries
    ]
    assert result.data["reversalTransactionId"] == reversal.id


async def test_reversal_returns_the_money_to_the_sender() -> None:
    service, parts = build_admin_service()
    original = await _posted_transfer(parts)
    sender = original.entries[0].account_id

    before = await parts["ledger"].balance_of(sender)
    await service._handle_reverse(
        ReverseTransaction(transaction_id=original.id, reason="Returned to sender"),
        admin_context(),
        session=None,
    )
    after = await parts["ledger"].balance_of(sender)

    assert before == -125_00
    assert after == 0


async def test_the_same_transaction_cannot_be_reversed_twice() -> None:
    service, parts = build_admin_service()
    original = await _posted_transfer(parts)
    command = ReverseTransaction(
        transaction_id=original.id, reason="Duplicate charge on the card"
    )

    await service._handle_reverse(command, admin_context(), session=None)

    with pytest.raises(ConflictError):
        await service._handle_reverse(command, admin_context(), session=None)
    assert len(parts["journal"].transactions) == 2


async def test_a_reversal_needs_a_reason() -> None:
    service, parts = build_admin_service()
    original = await _posted_transfer(parts)

    with pytest.raises(ValidationError):
        await service._handle_reverse(
            ReverseTransaction(transaction_id=original.id, reason="   "),
            admin_context(),
            session=None,
        )
    assert len(parts["journal"].transactions) == 1


async def test_a_customer_actor_cannot_reverse_a_transaction() -> None:
    service, parts = build_admin_service()
    original = await _posted_transfer(parts)

    with pytest.raises(AuthorizationError):
        await service._handle_reverse(
            ReverseTransaction(transaction_id=original.id, reason="Not mine at all"),
            customer_context(),
            session=None,
        )
    assert len(parts["journal"].transactions) == 1


async def test_reversing_an_unknown_transaction_is_a_not_found() -> None:
    service, _ = build_admin_service()

    with pytest.raises(NotFoundError):
        await service._handle_reverse(
            ReverseTransaction(transaction_id="nope", reason="Nothing to reverse"),
            admin_context(),
            session=None,
        )


async def test_any_transaction_in_the_journal_may_be_selected_including_a_reversal() -> None:
    service, parts = build_admin_service()
    original = await _posted_transfer(parts)
    first = await service._handle_reverse(
        ReverseTransaction(transaction_id=original.id, reason="Reversed in error"),
        admin_context(),
        session=None,
    )

    result = await service._handle_reverse(
        ReverseTransaction(
            transaction_id=first.data["reversalTransactionId"],
            reason="Undoing the reversal itself",
        ),
        admin_context(),
        session=None,
    )

    assert len(parts["journal"].transactions) == 3
    assert result.data["reversedTransactionId"] == first.data["reversalTransactionId"]
