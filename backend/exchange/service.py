from datetime import date
from functools import lru_cache
from typing import Any, ClassVar, NamedTuple, Protocol

from motor.motor_asyncio import AsyncIOMotorClientSession

from backend.accounts.account import AccountKind
from backend.accounts.service import AccountsService, get_accounts_service
from backend.command_bus import Command, CommandBus, CommandResult, bus
from backend.config import settings
from backend.database.records import AuditRecord, DomainEvent
from backend.exchange.adapters import FrankfurterRateClient
from backend.exchange.validation import convert_minor, normalise_pair
from backend.helpers.context import ActorContext
from backend.ledger.journal import (
    HouseAccount,
    JournalTransaction,
    TransactionKind,
    house_account_id,
)
from backend.ledger.service import LedgerService, get_ledger_service
from backend.ledger.validation import validate_minor_units


class BridgeResult(NamedTuple):
    source_transaction: JournalTransaction
    target_transaction: JournalTransaction
    target_amount_minor: int
    rate_micro: int
    as_of: str


class ConvertCurrency(Command):
    command_name: ClassVar[str] = "exchange.convert"

    source_account_id: str
    target_currency: str
    amount_minor: int


class RateSource(Protocol):
    async def fetch(self, base: str, quote: str) -> tuple[int, date]: ...


def _label_for(currency: str) -> str:
    return "Cont curent" if currency == "RON" else f"Cont curent {currency}"


class ExchangeService:
    def __init__(self, accounts: AccountsService, ledger: LedgerService, rates: RateSource) -> None:
        self._accounts = accounts
        self._ledger = ledger
        self._rates = rates

    def register(self, command_bus: CommandBus) -> None:
        command_bus.register(ConvertCurrency, self._handle_convert)

    async def rate(self, source_currency: str, target_currency: str) -> dict[str, Any]:
        source, target = normalise_pair(source_currency, target_currency)
        rate_micro, as_of = await self._rates.fetch(source, target)
        return {
            "from": source,
            "to": target,
            "rateMicro": rate_micro,
            "asOf": as_of.isoformat(),
        }

    async def bridge(
        self,
        *,
        session: AsyncIOMotorClientSession,
        context: ActorContext,
        source_account_id: str,
        target_account_id: str,
        amount_minor: int,
        source_currency: str,
        target_currency: str,
        reference: str,
        counterparty: str,
        category: str,
    ) -> BridgeResult:
        """Post the two FX legs that move money from one currency into another,
        via the house FX account. The only place `TransactionKind.FX_CONVERSION`
        legs get written — callers outside `exchange` reuse this instead of
        composing their own currency-crossing journal entries."""
        source_currency, target_currency = normalise_pair(source_currency, target_currency)
        rate_micro, as_of = await self._rates.fetch(source_currency, target_currency)
        target_amount = convert_minor(amount_minor, rate_micro)

        source_transaction = await self._ledger.post_transaction(
            currency=source_currency,
            kind=TransactionKind.FX_CONVERSION,
            legs=[
                (source_account_id, -amount_minor),
                (house_account_id(HouseAccount.FX, source_currency), amount_minor),
            ],
            reference=reference,
            counterparty=counterparty,
            category=category,
            correlation_id=context.correlation_id,
            actor=context.actor.label(),
            session=session,
        )
        target_transaction = await self._ledger.post_transaction(
            currency=target_currency,
            kind=TransactionKind.FX_CONVERSION,
            legs=[
                (house_account_id(HouseAccount.FX, target_currency), -target_amount),
                (target_account_id, target_amount),
            ],
            reference=reference,
            counterparty=counterparty,
            category=category,
            correlation_id=context.correlation_id,
            actor=context.actor.label(),
            session=session,
        )

        return BridgeResult(
            source_transaction, target_transaction, target_amount, rate_micro, as_of.isoformat()
        )

    async def _resolve_target_account(
        self, user_id: str, holder_name: str, currency: str, session: AsyncIOMotorClientSession
    ):
        owned = await self._accounts.owned_accounts(user_id)
        for account in owned:
            if account.currency == currency and account.status == "active":
                return account
        return await self._accounts.open_account(
            user_id=user_id,
            holder_name=holder_name,
            currency=currency,
            kind=AccountKind.CURRENT,
            label=_label_for(currency),
            session=session,
        )

    async def _handle_convert(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, ConvertCurrency)
        user_id = context.actor.id

        amount = validate_minor_units(command.amount_minor)
        source = await self._accounts.get_owned(command.source_account_id, user_id)
        source.guard_can_send()

        source_currency, target_currency = normalise_pair(source.currency, command.target_currency)

        balance = await self._ledger.balance_of(source.id)
        source.guard_sufficient(balance, amount)

        target = await self._resolve_target_account(
            user_id, source.holder_name, target_currency, session
        )
        target.guard_can_receive()
        target_balance_before = await self._ledger.balance_of(target.id)

        reference = f"Schimb valutar {source_currency}→{target_currency}"

        result = await self.bridge(
            session=session,
            context=context,
            source_account_id=source.id,
            target_account_id=target.id,
            amount_minor=amount,
            source_currency=source_currency,
            target_currency=target_currency,
            reference=reference,
            counterparty="GEMS Exchange",
            category="transfer",
        )
        target_amount, rate_micro = result.target_amount_minor, result.rate_micro

        receipt = {
            "sourceAccount": source.public_view(balance - amount),
            "targetAccount": target.public_view(target_balance_before + target_amount),
            "amountMinorUnits": amount,
            "targetAmountMinorUnits": target_amount,
            "rateMicro": rate_micro,
            "asOf": result.as_of,
        }

        return CommandResult(
            data=receipt,
            audit=AuditRecord(
                action="exchange.converted",
                entity_type="account",
                entity_id=source.id,
                after={
                    "sourceAccountId": source.id,
                    "targetAccountId": target.id,
                    "amountMinorUnits": amount,
                    "targetAmountMinorUnits": target_amount,
                    "rateMicro": rate_micro,
                },
            ),
            events=[
                DomainEvent(
                    name="exchange.converted",
                    aggregate_type="account",
                    aggregate_id=source.id,
                    payload={
                        "userId": user_id,
                        "sourceCurrency": source_currency,
                        "targetCurrency": target_currency,
                        "amountMinorUnits": amount,
                        "targetAmountMinorUnits": target_amount,
                    },
                )
            ],
        )


@lru_cache(maxsize=1)
def get_exchange_service() -> ExchangeService:
    service = ExchangeService(
        accounts=get_accounts_service(),
        ledger=get_ledger_service(),
        rates=FrankfurterRateClient(settings.frankfurter_base_url),
    )
    service.register(bus)
    return service
