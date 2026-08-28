from functools import lru_cache
from typing import Any, ClassVar, Protocol

from backend.accounts.service import AccountsService, get_accounts_service
from backend.command_bus import Command, CommandBus, CommandResult, bus
from backend.credits import validation
from backend.credits.application import CreditApplication
from backend.database.records import AuditRecord, DomainEvent
from backend.database.repositories import MongoCreditApplicationRepository
from backend.helpers.context import ActorContext
from backend.helpers.errors import IllegalTransitionError, NotFoundError
from motor.motor_asyncio import AsyncIOMotorClientSession

__all__ = ["CreditApplication", "CreditsService", "get_credits_service"]


class CreditApplicationRepository(Protocol):
    async def add(
        self, application: CreditApplication, session: AsyncIOMotorClientSession | None = None
    ) -> None: ...

    async def get(self, application_id: str) -> CreditApplication | None: ...

    async def list_for_user(self, user_id: str) -> list[CreditApplication]: ...

    async def set_status(
        self,
        application_id: str,
        user_id: str,
        status: str,
        session: AsyncIOMotorClientSession | None = None,
    ) -> bool: ...


class SubmitCreditApplication(Command):
    command_name: ClassVar[str] = "credits.apply"

    product_id: str
    amount_minor: int
    term_months: int | None
    purpose: str
    payout_account_id: str


class WithdrawCreditApplication(Command):
    command_name: ClassVar[str] = "credits.withdraw"

    application_id: str


class CreditsService:
    def __init__(
        self, applications: CreditApplicationRepository, accounts: AccountsService
    ) -> None:
        self._applications = applications
        self._accounts = accounts

    def register(self, command_bus: CommandBus) -> None:
        command_bus.register(SubmitCreditApplication, self._handle_submit)
        command_bus.register(WithdrawCreditApplication, self._handle_withdraw)

    async def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        applications = await self._applications.list_for_user(user_id)
        return [application.public_view() for application in applications]

    async def _handle_submit(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, SubmitCreditApplication)
        user_id = context.actor.subject_id()

        product = validation.product_for(command.product_id)
        amount = validation.normalise_amount_minor(command.amount_minor, product.max_minor)
        rate_bps = validation.rate_bps_for_term(product, command.term_months)
        purpose = validation.normalise_purpose(command.purpose)
        payout = await self._accounts.get_owned(command.payout_account_id, user_id)

        application = CreditApplication(
            user_id=user_id,
            product_id=product.id,
            kind=product.kind,
            amount_minor=amount,
            term_months=command.term_months,
            rate_bps=rate_bps,
            purpose=purpose,
            payout_account_id=payout.id,
            currency=product.currency,
        )
        await self._applications.add(application, session=session)

        view = application.public_view()
        return CommandResult(
            data=view,
            audit=AuditRecord(
                action="credits.applied",
                entity_type="creditApplication",
                entity_id=application.id,
                after=view,
            ),
            events=[
                DomainEvent(
                    name="credits.applied",
                    aggregate_type="creditApplication",
                    aggregate_id=application.id,
                    payload={"userId": user_id, "productId": product.id},
                )
            ],
        )

    async def _handle_withdraw(
        self, command: Command, context: ActorContext, session: AsyncIOMotorClientSession
    ) -> CommandResult:
        assert isinstance(command, WithdrawCreditApplication)
        user_id = context.actor.subject_id()

        application = await self._applications.get(command.application_id)
        if application is None or application.user_id != user_id:
            raise NotFoundError(
                "That application does not belong to you.", details={"field": "applicationId"}
            )
        if application.status != "review":
            raise IllegalTransitionError(
                "That application can no longer be withdrawn.",
                details={"field": "applicationId", "status": application.status},
            )

        changed = await self._applications.set_status(
            application.id, user_id, "withdrawn", session=session
        )
        if not changed:
            raise IllegalTransitionError(
                "That application can no longer be withdrawn.",
                details={"field": "applicationId"},
            )

        before = application.public_view()
        after = before | {"status": "withdrawn"}
        return CommandResult(
            data=after,
            audit=AuditRecord(
                action="credits.withdrawn",
                entity_type="creditApplication",
                entity_id=application.id,
                before=before,
                after=after,
            ),
            events=[
                DomainEvent(
                    name="credits.withdrawn",
                    aggregate_type="creditApplication",
                    aggregate_id=application.id,
                )
            ],
        )


@lru_cache(maxsize=1)
def get_credits_service() -> CreditsService:
    service = CreditsService(
        applications=MongoCreditApplicationRepository(),
        accounts=get_accounts_service(),
    )
    service.register(bus)
    return service
