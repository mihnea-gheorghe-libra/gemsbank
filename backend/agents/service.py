from functools import lru_cache

from backend.agents.adapters import AzureChatCompleter
from backend.agents.base import AgentAnswer
from backend.agents.support import SupportAgent
from backend.capabilities.service import get_capabilities_service
from backend.config import settings
from backend.database.records import write_audit
from backend.helpers.context import Actor


class SupportService:
    def __init__(self, agent: SupportAgent) -> None:
        self._agent = agent

    async def ask(self, user_id: str, question: str) -> AgentAnswer:
        agent_actor = Actor(kind="agent", id="support-agent", on_behalf_of=user_id)
        return await self._agent.ask(agent_actor, question)


@lru_cache(maxsize=1)
def get_support_service() -> SupportService:
    agent = SupportAgent(
        chat=AzureChatCompleter(settings),
        capabilities=get_capabilities_service(),
        audit=write_audit,
    )
    return SupportService(agent)
