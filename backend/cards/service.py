from datetime import date, datetime
from functools import lru_cache
from typing import Any, ClassVar, Protocol

from motor.motor_asyncio import AsyncIOMotorClientSession

from backend.accounts.service import AccountsService, get_accounts_service
from backend.cards import validation
from backend.cards.adapters import (
    RandomCardPinGenerator,
    RandomCvvGenerator,
    SyntheticCardNumberGenerator,
    SystemClock,
)
from backend.cards.card import Card, CardKind
from backend.command_bus import Command, CommandBus, CommandResult, bus
from backend.config import Settings, settings
from backend.database.records import AuditRecord, DomainEvent
from backend.database.repositories import MongoAuthUserRepository, MongoCardRepository
from backend.helpers.context import ActorContext, new_id
from backend.helpers.crypto import AesGcmPinCipher
from backend.helpers.errors import NotFoundError

DEFAULT_ATM_LIMIT_MINOR = 200_000  # RON 2 000,00
DEFAULT_ONLINE_LIMIT_MINOR = 400_000  # RON 4 000,00 — matches the mock's starter cap
VIRTUAL_CARD_VALIDITY_YEARS = 3
PHYSICAL_CARD_VALIDITY_YEARS = 5


class IssueVirtualCard(Command):
    command_name: ClassVar[str] = "cards.issue_virtual"

    username: str
    account_id: str


class IssuePhysicalCard(Command):
    command_name: ClassVar[str] = "cards.issue_physical"

    username: str
    account_id: str


class FreezeCard(Command):
    command_name: ClassVar[str] = "cards.freeze"

    username: str
    card_id: str


class UnfreezeCard(Command):
    command_name: ClassVar[str] = "cards.unfreeze"

    username: str
    card_id: str


class BlockCardPermanently(Command):
    command_name: ClassVar[str] = "cards.block"

    username: str
    card_id: str


class RevealCardPin(Command):
    command_name: ClassVar[str] = "cards.reveal_pin"

    username: str
    card_id: str


class RevealCardDetails(Command):
    command_name: ClassVar[str] = "cards.reveal_details"

    username: str
    card_id: str


class SetAtmLimit(Command):
    command_name: ClassVar[str] = "cards.set_atm_limit"

    username: str
    card_id: str
    limit_minor: int


class SetOnlineLimit(Command):
    command_name: ClassVar[str] = "cards.set_online_limit"

    username: str
    card_id: str
    limit_minor: int


class ResolvedUser(Protocol):
    id: str
    username: str

    @property
    def display_name(self) -> str: ...


class UserDirectory(Protocol):
    async def get_by_username(self, username: str) -> ResolvedUser | None: ...


class CardRepository(Protocol):
    async def add(self, card: Card, session: AsyncIOMotorClientSession | None = None) -> None: ...

    async def get(self, card_id: str) -> Card | None: ...

    async def list_for_user(self, user_id: str) -> list[Card]: ...

    async def save(self, card: Card, session: AsyncIOMotorClientSession | None = None) -> None: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class CardNumberGenerator(Protocol):
    def last4(self) -> str: ...


class CardPinGenerator(Protocol):
    def generate(self) -> str: ...


class CardCvvGenerator(Protocol):
    def generate(self) -> str: ...


class PinCipher(Protocol):
    def encrypt(self, plaintext: str, associated_data: str) -> str: ...

    def decrypt(self, ciphertext: str, associated_data: str) -> str: ...


def _years_from_now(now: datetime, years: int) -> date:
    try:
        return now.date().replace(year=now.year + years)
    except ValueError:
        # 29 Feb landing on a non-leap target year.
        return now.date().replace(year=now.year + years, day=28)


class CardsService:
    def __init__(
        self,
        cards: CardRepository,
        users: UserDirectory,
        accounts: AccountsService,
        numbers: CardNumberGenerator,
        pins: CardPinGenerator,
        cvvs: CardCvvGenerator,
        cipher: PinCipher,
        clock: Clock,
        config: Settings,
    ) -> None:
        self._cards = cards
        self._users = users
        self._accounts = accounts
        self._numbers = numbers
        self._pins = pins
        self._cvvs = cvvs
        self._cipher = cipher
        self._clock = clock
        self._config = config

    def register(self, command_bus: CommandBus) -> None:
        command_bus.register(IssueVirtualCard, self._handle_issue_virtual)
        command_bus.register(IssuePhysicalCard, self._handle_issue_physical)
        command_bus.register(FreezeCard, self._handle_freeze)
        command_bus.register(UnfreezeCard, self._handle_unfreeze)
        command_bus.register(BlockCardPermanently, self._handle_block)
        command_bus.register(RevealCardPin, self._handle_reveal_pin)
        command_bus.register(RevealCardDetails, self._handle_reveal_details)
        command_bus.register(SetAtmLimit, self._handle_set_atm_limit)
        command_bus.register(SetOnlineLimit, self._handle_set_online_limit)

    async def list_cards(self, username: str) -> dict[str, Any]:
        user = await self._require_user(username)
        cards = await self._cards.list_for_user(user.id)
        return {"cards": [card.public_view() for card in cards]}

    async def _require_user(self, username: str) -> ResolvedUser:
        user = await self._users.get_by_username(username.strip().lower())
        if user is None:
            raise NotFoundError(
                "No account uses that username.", details={"field": "username"}
            )
        return user

    async def _require_owned_card(self, username: str, card_id: str) -> tuple[ResolvedUser, Card]:
        user = await self._require_user(username)
        card = await self._cards.get(card_id)
        if card is None or card.user_id != user.id:
            raise NotFoundError(
                "No card matches that id for this account.", details={"field": "cardId"}
            )
        return user, card

    async def _issue(
        self,
        username: str,
        account_id: str,
        kind: CardKind,
        validity_years: int,
        session: AsyncIOMotorClientSession,
    ) -> CommandResult:
        user = await self._require_user(username)
        account = await self._accounts.get_owned(account_id, user.id)

        card_id = new_id()
        pin = self._pins.generate()
        cvv = self._cvvs.generate()
        card = Card(
            id=card_id,
            user_id=user.id,
            account_id=account.id,
            kind=kind,
            last4=self._numbers.last4(),
            owner_name=user.username.upper(),
            currency=account.currency,
            expires_on=_years_from_now(self._clock.now(), validity_years),
            pin_encrypted=self._cipher.encrypt(pin, associated_data=card_id),
            cvv_encrypted=self._cipher.encrypt(cvv, associated_data=card_id + ":cvv"),
            atm_limit_minor=DEFAULT_ATM_LIMIT_MINOR,
            online_limit_minor=DEFAULT_ONLINE_LIMIT_MINOR,
        )
        await self._cards.add(card, session=session)

        return CommandResult(
            data=card.public_view(),
            audit=AuditRecord(
                action="cards.issued",
                entity_type="card",
                entity_id=card.id,
                after=card.public_view() | {"userId": user.id},
            ),
            events=[
                DomainEvent(
                    name="cards.issued",
                    aggregate_type="card",
                    aggregate_id=card.id,
                    payload={"userId": user.id},
                )
            ],
        )

    async def _handle_issue_virtual(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, IssueVirtualCard)
        return await self._issue(
            command.username,
            command.account_id,
            CardKind.VIRTUAL_MASTERCARD,
            VIRTUAL_CARD_VALIDITY_YEARS,
            session,
        )

    async def _handle_issue_physical(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, IssuePhysicalCard)
        return await self._issue(
            command.username,
            command.account_id,
            CardKind.PHYSICAL_DEBIT,
            PHYSICAL_CARD_VALIDITY_YEARS,
            session,
        )

    async def _handle_freeze(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, FreezeCard)
        user, card = await self._require_owned_card(command.username, command.card_id)
        before = card.state.value
        card.freeze()
        await self._cards.save(card, session=session)

        return CommandResult(
            data=card.public_view(),
            audit=AuditRecord(
                action="cards.frozen",
                entity_type="card",
                entity_id=card.id,
                before={"state": before},
                after={"state": card.state.value, "userId": user.id},
            ),
            events=[
                DomainEvent(
                    name="cards.frozen",
                    aggregate_type="card",
                    aggregate_id=card.id,
                    payload={"userId": user.id},
                )
            ],
        )

    async def _handle_unfreeze(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, UnfreezeCard)
        user, card = await self._require_owned_card(command.username, command.card_id)
        before = card.state.value
        card.unfreeze()
        await self._cards.save(card, session=session)

        return CommandResult(
            data=card.public_view(),
            audit=AuditRecord(
                action="cards.unfrozen",
                entity_type="card",
                entity_id=card.id,
                before={"state": before},
                after={"state": card.state.value, "userId": user.id},
            ),
            events=[
                DomainEvent(
                    name="cards.unfrozen",
                    aggregate_type="card",
                    aggregate_id=card.id,
                    payload={"userId": user.id},
                )
            ],
        )

    async def _handle_block(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, BlockCardPermanently)
        user, card = await self._require_owned_card(command.username, command.card_id)
        before = card.state.value
        card.block_permanently()
        await self._cards.save(card, session=session)

        return CommandResult(
            data=card.public_view(),
            audit=AuditRecord(
                action="cards.blocked",
                entity_type="card",
                entity_id=card.id,
                before={"state": before},
                after={"state": card.state.value, "userId": user.id},
            ),
            events=[
                DomainEvent(
                    name="cards.blocked",
                    aggregate_type="card",
                    aggregate_id=card.id,
                    payload={"userId": user.id},
                )
            ],
        )

    async def _handle_reveal_pin(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, RevealCardPin)
        user, card = await self._require_owned_card(command.username, command.card_id)
        card.require_revealable()
        pin = self._cipher.decrypt(card.pin_encrypted, associated_data=card.id)

        return CommandResult(
            data=card.public_view(),
            sensitive={"pin": pin},
            audit=AuditRecord(
                action="cards.pin_revealed",
                entity_type="card",
                entity_id=card.id,
                after={"userId": user.id},
            ),
            events=[
                DomainEvent(
                    name="cards.pin_revealed",
                    aggregate_type="card",
                    aggregate_id=card.id,
                    payload={"userId": user.id},
                )
            ],
        )

    async def _handle_reveal_details(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, RevealCardDetails)
        user, card = await self._require_owned_card(command.username, command.card_id)
        cvv_encrypted = card.require_cvv_revealable()
        cvv = self._cipher.decrypt(cvv_encrypted, associated_data=card.id + ":cvv")

        return CommandResult(
            data=card.public_view(),
            sensitive={"cvv": cvv},
            audit=AuditRecord(
                action="cards.details_revealed",
                entity_type="card",
                entity_id=card.id,
                after={"userId": user.id},
            ),
            events=[
                DomainEvent(
                    name="cards.details_revealed",
                    aggregate_type="card",
                    aggregate_id=card.id,
                    payload={"userId": user.id},
                )
            ],
        )

    async def _handle_set_atm_limit(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, SetAtmLimit)
        user, card = await self._require_owned_card(command.username, command.card_id)
        before = card.atm_limit_minor
        limit = validation.validate_limit_minor(command.limit_minor, field="atmLimitMinor")
        card.set_atm_limit(limit)
        await self._cards.save(card, session=session)

        return CommandResult(
            data=card.public_view(),
            audit=AuditRecord(
                action="cards.atm_limit_set",
                entity_type="card",
                entity_id=card.id,
                before={"atmLimitMinor": before},
                after={"atmLimitMinor": card.atm_limit_minor, "userId": user.id},
            ),
            events=[
                DomainEvent(
                    name="cards.atm_limit_set",
                    aggregate_type="card",
                    aggregate_id=card.id,
                    payload={"userId": user.id, "limitMinor": card.atm_limit_minor},
                )
            ],
        )

    async def _handle_set_online_limit(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, SetOnlineLimit)
        user, card = await self._require_owned_card(command.username, command.card_id)
        before = card.online_limit_minor
        limit = validation.validate_limit_minor(command.limit_minor, field="onlineLimitMinor")
        card.set_online_limit(limit)
        await self._cards.save(card, session=session)

        return CommandResult(
            data=card.public_view(),
            audit=AuditRecord(
                action="cards.online_limit_set",
                entity_type="card",
                entity_id=card.id,
                before={"onlineLimitMinor": before},
                after={"onlineLimitMinor": card.online_limit_minor, "userId": user.id},
            ),
            events=[
                DomainEvent(
                    name="cards.online_limit_set",
                    aggregate_type="card",
                    aggregate_id=card.id,
                    payload={"userId": user.id, "limitMinor": card.online_limit_minor},
                )
            ],
        )


@lru_cache(maxsize=1)
def get_cards_service() -> CardsService:
    service = CardsService(
        cards=MongoCardRepository(),
        users=MongoAuthUserRepository(),
        accounts=get_accounts_service(),
        numbers=SyntheticCardNumberGenerator(),
        pins=RandomCardPinGenerator(),
        cvvs=RandomCvvGenerator(),
        cipher=AesGcmPinCipher(settings.pin_encryption_key),
        clock=SystemClock(),
        config=settings,
    )
    service.register(bus)
    return service
