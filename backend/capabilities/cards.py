from typing import Literal

from backend.capabilities.payments import format_minor
from backend.cards.service import CardsService, get_cards_service
from backend.helpers.context import Actor
from pydantic import BaseModel, Field

CardAction = Literal[
    "freeze",
    "unfreeze",
    "block",
    "set_atm_limit",
    "set_online_limit",
    "issue_virtual",
    "issue_physical",
    "reveal_pin",
    "reveal_details",
]

_CARD_ACTIONS_ON_A_CARD = {
    "freeze",
    "unfreeze",
    "block",
    "set_atm_limit",
    "set_online_limit",
    "reveal_pin",
    "reveal_details",
}

_NEEDS_LIMIT = {"set_atm_limit", "set_online_limit"}

_IRREVERSIBLE = {"block"}

_REQUIRED_STATE = {
    "freeze": ("active",),
    "unfreeze": ("frozen",),
    "block": ("active", "frozen"),
    "set_atm_limit": ("active", "frozen"),
    "set_online_limit": ("active", "frozen"),
    "reveal_pin": ("active", "frozen"),
    "reveal_details": ("active", "frozen"),
}

_MAX_LIMIT_MINOR = 5_000_000


class CardView(BaseModel):
    card_id: str = Field(alias="cardId")
    kind: str
    number_masked: str = Field(alias="numberMasked")
    owner: str
    currency: str
    expires_on: str = Field(alias="expiresOn")
    state: str
    atm_limit_formatted: str = Field(alias="atmLimitFormatted")
    online_limit_formatted: str = Field(alias="onlineLimitFormatted")
    model_config = {"populate_by_name": True}


class CardsListInput(BaseModel):
    pass


class CardsListOutput(BaseModel):
    status: Literal["ok", "no_cards"]
    cards: list[CardView] = Field(default_factory=list)
    note: str = (
        "A card's full number, PIN and CVV are never shown here. If the customer wants those, "
        "propose reveal_pin or reveal_details and they will see them on screen, not in chat."
    )


class CardActionInput(BaseModel):
    action: CardAction = Field(
        description="What the customer wants done. One action per proposal."
    )
    card_id: str | None = Field(
        default=None,
        alias="cardId",
        max_length=64,
        description=(
            "Which card, by its cardId from cards.list. Required for everything except "
            "issue_virtual and issue_physical. Never guess it."
        ),
    )
    limit_minor: int | None = Field(
        default=None,
        alias="limitMinorUnits",
        ge=0,
        le=_MAX_LIMIT_MINOR,
        description="The new limit in integer minor units. Only for the two set_*_limit actions.",
    )
    model_config = {"populate_by_name": True}


class ActionBlocker(BaseModel):
    code: str
    message: str


class CardActionOutput(BaseModel):
    status: Literal["proposed", "blocked", "needs_clarification"]
    action: str
    card_id: str | None = Field(default=None, alias="cardId")
    card_label: str | None = Field(default=None, alias="cardLabel")
    current_state: str | None = Field(default=None, alias="currentState")
    limit_minor: int | None = Field(default=None, alias="limitMinorUnits")
    limit_formatted: str | None = Field(default=None, alias="limitFormatted")
    irreversible: bool = False
    reveals_secret: bool = Field(default=False, alias="revealsSecret")
    requires_human_confirmation: bool = Field(default=True, alias="requiresHumanConfirmation")
    candidates: list[CardView] = Field(default_factory=list)
    blockers: list[ActionBlocker] = Field(default_factory=list)
    model_config = {"populate_by_name": True}


def _card_view(raw: dict) -> CardView:
    currency = raw.get("currency", "RON")
    return CardView(
        cardId=raw["cardId"],
        kind=raw["kind"],
        numberMasked=raw["numberMasked"],
        owner=raw["owner"],
        currency=currency,
        expiresOn=raw["expiresOn"],
        state=raw["state"],
        atmLimitFormatted=format_minor(raw.get("atmLimitMinor") or 0, currency),
        onlineLimitFormatted=format_minor(raw.get("onlineLimitMinor") or 0, currency),
    )


def _label(raw: dict) -> str:
    return f"{raw['kind'].replace('_', ' ')} {raw['numberMasked']}"


async def _cards_for(actor: Actor, service: CardsService) -> list[dict]:
    data = await service.list_cards(actor.subject_id())
    return data["cards"]


async def resolve_cards_list(
    actor: Actor, payload: BaseModel, cards_service: CardsService | None = None
) -> BaseModel:
    assert isinstance(payload, CardsListInput)
    rows = await _cards_for(actor, cards_service or get_cards_service())
    if not rows:
        return CardsListOutput(status="no_cards")
    return CardsListOutput(status="ok", cards=[_card_view(row) for row in rows])


async def resolve_card_action(
    actor: Actor, payload: BaseModel, cards_service: CardsService | None = None
) -> BaseModel:
    assert isinstance(payload, CardActionInput)
    rows = await _cards_for(actor, cards_service or get_cards_service())
    action = payload.action

    if action in _NEEDS_LIMIT and payload.limit_minor is None:
        return CardActionOutput(
            status="needs_clarification",
            action=action,
            blockers=[
                ActionBlocker(
                    code="limit_missing",
                    message="Ask the customer what the new limit should be.",
                )
            ],
        )

    if action not in _CARD_ACTIONS_ON_A_CARD:
        return CardActionOutput(
            status="proposed",
            action=action,
            requiresHumanConfirmation=True,
        )

    if not rows:
        return CardActionOutput(
            status="blocked",
            action=action,
            blockers=[
                ActionBlocker(code="no_cards", message="This customer holds no cards yet.")
            ],
        )

    if not payload.card_id:
        return CardActionOutput(
            status="needs_clarification",
            action=action,
            candidates=[_card_view(row) for row in rows],
            blockers=[
                ActionBlocker(
                    code="card_not_named",
                    message="Ask which card they mean and list the candidates.",
                )
            ],
        )

    card = next((row for row in rows if row["cardId"] == payload.card_id), None)
    if card is None:
        return CardActionOutput(
            status="needs_clarification",
            action=action,
            candidates=[_card_view(row) for row in rows],
            blockers=[
                ActionBlocker(
                    code="card_not_found",
                    message="No card of theirs has that id.",
                )
            ],
        )

    state = card["state"]
    allowed = _REQUIRED_STATE.get(action, ())
    if state not in allowed:
        return CardActionOutput(
            status="blocked",
            action=action,
            cardId=card["cardId"],
            cardLabel=_label(card),
            currentState=state,
            blockers=[
                ActionBlocker(
                    code="illegal_transition",
                    message=f"That card is {state}, so this cannot be done to it.",
                )
            ],
        )

    currency = card.get("currency", "RON")
    return CardActionOutput(
        status="proposed",
        action=action,
        cardId=card["cardId"],
        cardLabel=_label(card),
        currentState=state,
        limitMinorUnits=payload.limit_minor,
        limitFormatted=(
            format_minor(payload.limit_minor, currency)
            if payload.limit_minor is not None
            else None
        ),
        irreversible=action in _IRREVERSIBLE,
        revealsSecret=action in {"reveal_pin", "reveal_details"},
        requiresHumanConfirmation=True,
    )
