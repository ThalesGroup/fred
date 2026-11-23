"""Deliver durable in-thread user updates at safe model boundaries."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fred_core.history.history_schema import TextPart
from fred_core.history.postgres_history_store import PostgresHistoryStore
from fred_sdk.contracts.runtime import SteeredUserMessageRuntimeEvent
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import HumanMessage
from langgraph.config import get_stream_writer

from fred_runtime.runtime_support.run_scope import RunScope

logger = logging.getLogger(__name__)


class TurnMessages:
    def __init__(self) -> None:
        self._history: PostgresHistoryStore | None = None

    def configure(self, history: PostgresHistoryStore | None) -> None:
        self._history = history

    def require_history(self) -> PostgresHistoryStore:
        if self._history is None:
            raise RuntimeError("Turn message history is not configured")
        return self._history


turn_messages = TurnMessages()


def steered_human_message(message_id: str, content: str) -> HumanMessage:
    return HumanMessage(
        id=f"steered:{message_id}",
        content="The user has sent an update while this task is in progress. "
        "Apply this latest instruction before deciding what to do next; "
        "it may add information, revise or cancel the earlier request. "
        "Answer any outstanding question in the final response. "
        "If the user asks you to stop, do not call more tools; "
        f"briefly acknowledge and end the turn.\n\n{content}",
    )


class TurnSteeringMiddleware(AgentMiddleware):
    def __init__(
        self,
        session_id: str | None,
        pending_message_id: str | None = None,
        exchange_id: str | None = None,
        user_id: str | None = None,
        agent_instance_id: str | None = None,
    ) -> None:
        super().__init__()
        self._session_id = session_id
        self._pending_message_id = pending_message_id
        self._exchange_id = exchange_id
        self._user_id = user_id
        self._agent_instance_id = agent_instance_id
        self._pending_delivery: tuple[tuple[str, str], ...] = ()

    async def abefore_model(self, state, runtime) -> dict | None:
        if not self._session_id or not self._agent_instance_id:
            return None
        history = turn_messages.require_history()
        pending = await history.pending_steered_messages(
            self._session_id, self._user_id, self._agent_instance_id
        )
        if not pending:
            self._pending_delivery = ()
            return None
        seen_ids = {
            str(message.id)
            for message in state.get("messages", [])
            if getattr(message, "id", None)
        }
        injected: list[tuple[int, HumanMessage]] = []
        pending_delivery: list[tuple[str, str]] = []
        for message in pending:
            extras = (message.metadata.model_extra or {}).get("extras")
            message_id = (
                extras.get("steered_message_id") if isinstance(extras, dict) else None
            )
            part = message.parts[0] if message.parts else None
            if not isinstance(message_id, str) or not isinstance(part, TextPart):
                continue
            content = part.text
            if message_id != self._pending_message_id:
                stable_id = f"steered:{message_id}"
                if stable_id not in seen_ids:
                    injected.append(
                        (
                            message.rank,
                            steered_human_message(message_id, content),
                        )
                    )
            pending_delivery.append((message_id, content))
        self._pending_delivery = tuple(pending_delivery)
        injected.sort(key=lambda item: (0, item[0]) if item[0] >= 0 else (1, -item[0]))
        return {"messages": [item for _, item in injected]} if injected else None

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        pending_delivery = self._pending_delivery
        self._pending_delivery = ()
        if pending_delivery:
            scope = RunScope.current()
            if scope is None:
                raise RuntimeError("Steered delivery has no active run scope")
            writer = get_stream_writer()
            for message_id, content in pending_delivery:
                receipt_key = f"steered-user:{message_id}"
                receipt = scope.register_event_receipt(receipt_key)
                try:
                    writer(
                        SteeredUserMessageRuntimeEvent(
                            message_id=message_id, content=content
                        )
                    )
                    await receipt
                finally:
                    scope.discard_event_receipt(receipt_key)
        return await handler(request)
