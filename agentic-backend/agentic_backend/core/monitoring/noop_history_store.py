# Copyright Thales 2025
#
# Apache 2.0

from typing import Dict, List

from agentic_backend.core.chatbot.chat_schema import ChatMessage
from agentic_backend.core.chatbot.metric_structures import MetricsResponse

from .base_history_store import BaseHistoryStore  # adjust import to your path


class NoOpHistoryStore(BaseHistoryStore):
    """
    Fred rationale:
    - In tests, we often want to exercise the agent's orchestration (planning, tools)
      without coupling to persistence. This store "accepts" writes but never stores,
      and always returns an empty history on reads.
    - This prevents flakiness from IO/mappings while keeping the same interface.
    """

    async def save(
        self, session_id: str, messages: List[ChatMessage], user_id: str
    ) -> None:
        # Intentionally do nothing: the contract is "fire-and-forget".
        # Why: Tests that focus on reasoning should not assert on storage side-effects.
        return

    async def get(self, session_id: str) -> List[ChatMessage]:
        # Always return an empty transcript.
        # Why: Each test starts with a clean slate unless you explicitly fake history upstream.
        return []

    async def save_with_conn(
        self, conn, session_id: str, messages: List[ChatMessage], user_id: str
    ) -> None:
        # Same no-op behavior for transactional path.
        return

    async def get_chatbot_metrics(
        self,
        start: str,
        end: str,
        user_id: str,
        precision: str,
        groupby: List[str],
        agg_mapping: Dict[str, List[str]],
    ) -> MetricsResponse:
        # No metrics are computed in NoOp mode. We raise to make accidental
        # production usage noisy while keeping unit tests explicit.
        raise NotImplementedError(
            "NoOpHistoryStore does not compute metrics. "
            "Use a real store (e.g., OpenSearchHistoryStore) or a metrics stub in tests."
        )
