from functools import lru_cache

from pydantic import BaseModel, Field

from backend.auth.service import get_auth_service
from backend.capabilities import analytics
from backend.capabilities import cards as cards_capabilities
from backend.capabilities import investments as investments_capabilities
from backend.capabilities import payments as payments_capabilities
from backend.capabilities import products as products_capabilities
from backend.capabilities.registry import (
    Capability,
    CapabilityRegistry,
    SideEffect,
    registry,
)
from backend.capabilities.support_docs import search_support_docs
from backend.helpers.context import Actor


class SupportSearchInput(BaseModel):
    query: str = Field(default="", max_length=200)


class SupportDocView(BaseModel):
    id: str
    label_en: str = Field(alias="labelEn")
    label_ro: str = Field(alias="labelRo")
    body_en: str = Field(alias="bodyEn")
    body_ro: str = Field(alias="bodyRo")
    model_config = {"populate_by_name": True}


class SupportSearchOutput(BaseModel):
    results: list[SupportDocView]


class ProfileInput(BaseModel):
    pass


class ProfileOutput(BaseModel):
    username: str
    email: str
    phone: str
    full_name: str = Field(alias="fullName")
    model_config = {"populate_by_name": True}


class PreferencesInput(BaseModel):
    pass


class PreferencesOutput(BaseModel):
    lang: str
    theme: str


class SessionsInput(BaseModel):
    pass


class SessionView(BaseModel):
    session_id: str = Field(alias="sessionId")
    device: str
    location: str
    issued_at: str = Field(alias="issuedAt")
    model_config = {"populate_by_name": True}


class SessionsOutput(BaseModel):
    sessions: list[SessionView]


async def _resolve_support_search(_actor: Actor, payload: BaseModel) -> BaseModel:
    assert isinstance(payload, SupportSearchInput)
    docs = search_support_docs(payload.query)
    return SupportSearchOutput(
        results=[
            SupportDocView(
                id=doc.id,
                labelEn=doc.label_en,
                labelRo=doc.label_ro,
                bodyEn=doc.body_en,
                bodyRo=doc.body_ro,
            )
            for doc in docs
        ]
    )


async def _resolve_profile(actor: Actor, payload: BaseModel) -> BaseModel:
    data = await get_auth_service().get_me(actor.subject_id())
    return ProfileOutput(
        username=data["username"],
        email=data["email"],
        phone=data["phone"],
        fullName=data["fullName"],
    )


async def _resolve_preferences(actor: Actor, payload: BaseModel) -> BaseModel:
    data = await get_auth_service().get_me(actor.subject_id())
    prefs = data.get("prefs") or {}
    return PreferencesOutput(lang=prefs.get("lang", "ro"), theme=prefs.get("theme", "light"))


async def _resolve_sessions(actor: Actor, payload: BaseModel) -> BaseModel:
    data = await get_auth_service().list_sessions(actor.subject_id(), current_token="")
    return SessionsOutput(
        sessions=[
            SessionView(
                sessionId=row["sessionId"],
                device=row["device"],
                location=row["location"],
                issuedAt=row["issuedAt"],
            )
            for row in data["sessions"]
        ]
    )


@lru_cache(maxsize=1)
def get_capabilities_service() -> CapabilityRegistry:
    registry.register(
        Capability(
            name="support.faq.search",
            input_schema=SupportSearchInput,
            output_schema=SupportSearchOutput,
            side_effect=SideEffect.READ,
            required_scope="support:read",
            resolver=_resolve_support_search,
        )
    )
    registry.register(
        Capability(
            name="settings.profile.get",
            input_schema=ProfileInput,
            output_schema=ProfileOutput,
            side_effect=SideEffect.READ,
            required_scope="profile:read",
            resolver=_resolve_profile,
        )
    )
    registry.register(
        Capability(
            name="settings.preferences.get",
            input_schema=PreferencesInput,
            output_schema=PreferencesOutput,
            side_effect=SideEffect.READ,
            required_scope="preferences:read",
            resolver=_resolve_preferences,
        )
    )
    registry.register(
        Capability(
            name="settings.sessions.list",
            input_schema=SessionsInput,
            output_schema=SessionsOutput,
            side_effect=SideEffect.READ,
            required_scope="sessions:read",
            resolver=_resolve_sessions,
        )
    )
    registry.register(
        Capability(
            name="analytics.cashflow_forecast.get",
            input_schema=analytics.CashflowForecastInput,
            output_schema=analytics.CashflowForecastOutput,
            side_effect=SideEffect.READ,
            required_scope="analytics:read",
            resolver=analytics.resolve_cashflow_forecast,
        )
    )
    registry.register(
        Capability(
            name="analytics.goal_gap.get",
            input_schema=analytics.GoalGapInput,
            output_schema=analytics.GoalGapOutput,
            side_effect=SideEffect.READ,
            required_scope="goals:read",
            resolver=analytics.resolve_goal_gap,
        )
    )
    registry.register(
        Capability(
            name="analytics.month_recap.get",
            input_schema=analytics.MonthRecapInput,
            output_schema=analytics.MonthRecapOutput,
            side_effect=SideEffect.READ,
            required_scope="analytics:read",
            resolver=analytics.resolve_month_recap,
        )
    )
    registry.register(
        Capability(
            name="analytics.what_changed.get",
            input_schema=analytics.WhatChangedInput,
            output_schema=analytics.WhatChangedOutput,
            side_effect=SideEffect.READ,
            required_scope="analytics:read",
            resolver=analytics.resolve_what_changed,
        )
    )
    registry.register(
        Capability(
            name="analytics.recommendations.get",
            input_schema=analytics.RecommendationsInput,
            output_schema=analytics.RecommendationsOutput,
            side_effect=SideEffect.READ,
            required_scope="analytics:read",
            resolver=analytics.resolve_recommendations,
        )
    )
    registry.register(
        Capability(
            name="payments.balances.get",
            input_schema=payments_capabilities.BalancesInput,
            output_schema=payments_capabilities.BalancesOutput,
            side_effect=SideEffect.READ,
            required_scope="accounts:read",
            resolver=payments_capabilities.resolve_balances,
        )
    )
    registry.register(
        Capability(
            name="payments.beneficiaries.list",
            input_schema=payments_capabilities.BeneficiariesInput,
            output_schema=payments_capabilities.BeneficiariesOutput,
            side_effect=SideEffect.READ,
            required_scope="beneficiaries:read",
            resolver=payments_capabilities.resolve_beneficiaries,
        )
    )
    registry.register(
        Capability(
            name="payments.transfer.propose",
            input_schema=payments_capabilities.TransferProposalInput,
            output_schema=payments_capabilities.TransferProposalOutput,
            side_effect=SideEffect.MONEY_MOVING,
            required_scope="payments:propose",
            resolver=payments_capabilities.resolve_transfer_proposal,
        )
    )
    registry.register(
        Capability(
            name="investments.market.get",
            input_schema=investments_capabilities.MarketInput,
            output_schema=investments_capabilities.MarketOutput,
            side_effect=SideEffect.READ,
            required_scope="investments:read",
            resolver=investments_capabilities.resolve_market,
        )
    )
    registry.register(
        Capability(
            name="deposits.products.list",
            input_schema=products_capabilities.DepositProductsInput,
            output_schema=products_capabilities.DepositProductsOutput,
            side_effect=SideEffect.READ,
            required_scope="products:read",
            resolver=products_capabilities.resolve_deposit_products,
        )
    )
    registry.register(
        Capability(
            name="deposits.maturity.estimate",
            input_schema=products_capabilities.MaturityInput,
            output_schema=products_capabilities.MaturityOutput,
            side_effect=SideEffect.READ,
            required_scope="products:read",
            resolver=products_capabilities.resolve_maturity_estimate,
        )
    )
    registry.register(
        Capability(
            name="credits.products.list",
            input_schema=products_capabilities.CreditProductsInput,
            output_schema=products_capabilities.CreditProductsOutput,
            side_effect=SideEffect.READ,
            required_scope="products:read",
            resolver=products_capabilities.resolve_credit_products,
        )
    )
    registry.register(
        Capability(
            name="credits.repayment.estimate",
            input_schema=products_capabilities.RepaymentInput,
            output_schema=products_capabilities.RepaymentOutput,
            side_effect=SideEffect.READ,
            required_scope="products:read",
            resolver=products_capabilities.resolve_repayment_estimate,
        )
    )
    registry.register(
        Capability(
            name="cards.list",
            input_schema=cards_capabilities.CardsListInput,
            output_schema=cards_capabilities.CardsListOutput,
            side_effect=SideEffect.READ,
            required_scope="cards:read",
            resolver=cards_capabilities.resolve_cards_list,
        )
    )
    registry.register(
        Capability(
            name="cards.action.propose",
            input_schema=cards_capabilities.CardActionInput,
            output_schema=cards_capabilities.CardActionOutput,
            side_effect=SideEffect.WRITE,
            required_scope="cards:propose",
            resolver=cards_capabilities.resolve_card_action,
        )
    )
    return registry
