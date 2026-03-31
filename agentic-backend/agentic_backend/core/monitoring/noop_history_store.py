# Copyright Thales 2025
#
# Apache 2.0

from typing import Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from agentic_backend.core.chatbot.chat_schema import ChatMessage
from agentic_backend.core.chatbot.metric_structures import MetricsResponse

from .base_history_store import BaseHistoryStore


class NoOpHistoryStore(BaseHistoryStore):
    """
    Fred rationale:
    - In tests, we often want to exercise the agent's orchestration (planning, tools)
      without coupling to persistence. This store "accepts" writes but never stores,
      and always returns an empty history on reads.
    - This prevents flakiness from IO/mappings while keeping the same interface.
    """

    async def save(
        self,
        session_id: str,
        messages: List[ChatMessage],
        user_id: str,
        session: AsyncSession | None = None,
    ) -> None:
        return

    async def get(
        self, session_id: str, session: AsyncSession | None = None
    ) -> List[ChatMessage]:
        return []

    async def get_chatbot_metrics(
        self,
        start: str,
        end: str,
        user_id: str,
        precision: str,
        groupby: List[str],
        agg_mapping: Dict[str, List[str]],
        session: AsyncSession | None = None,
    ) -> MetricsResponse:
        raise NotImplementedError(
            "NoOpHistoryStore does not compute metrics. "
            "Use a real store (e.g., OpenSearchHistoryStore) or a metrics stub in tests."
        )
