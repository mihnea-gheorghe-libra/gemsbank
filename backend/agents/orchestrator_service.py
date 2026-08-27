from functools import lru_cache

from backend.agents.adapters import AzureChatCompleter
from backend.agents.analytics import AnalyticsAgent
from backend.agents.cards import CardsAgent
from backend.agents.credits import CreditsAgent
from backend.agents.deposits import DepositsAgent
from backend.agents.education import EducationAgent
from backend.agents.investments import InvestmentsAgent
from backend.agents.orchestrator import OrchestratedAnswer, Orchestrator
from backend.agents.payments import PaymentsAgent
from backend.agents.support import SupportAgent
from backend.capabilities.service import get_capabilities_service
from backend.config import settings
from backend.database.records import write_audit
from backend.helpers.context import Actor


class OrchestratorService:
    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    async def ask(
        self,
        user_id: str,
        question: str,
        history: list[dict[str, str]] | None = None,
        screen: str | None = None,
    ) -> OrchestratedAnswer:
        actor = Actor(kind="agent", id="orchestrator", on_behalf_of=user_id)
        return await self._orchestrator.ask(actor, question, history=history, screen=screen)


@lru_cache(maxsize=1)
def get_orchestrator_service() -> OrchestratorService:
    chat = AzureChatCompleter(settings)
    capabilities = get_capabilities_service()
    workers = {
        "support": SupportAgent(chat=chat, capabilities=capabilities, audit=write_audit),
        "analytics": AnalyticsAgent(chat=chat, capabilities=capabilities, audit=write_audit),
        "payments": PaymentsAgent(chat=chat, capabilities=capabilities, audit=write_audit),
        "education": EducationAgent(chat=chat, capabilities=capabilities, audit=write_audit),
        "investments": InvestmentsAgent(chat=chat, capabilities=capabilities, audit=write_audit),
        "deposits": DepositsAgent(chat=chat, capabilities=capabilities, audit=write_audit),
        "credits": CreditsAgent(chat=chat, capabilities=capabilities, audit=write_audit),
        "cards": CardsAgent(chat=chat, capabilities=capabilities, audit=write_audit),
    }
    orchestrator = Orchestrator(chat=chat, workers=workers, audit=write_audit)
    return OrchestratorService(orchestrator)
