"""Deliver durable in-thread user updates at safe model boundaries."""

from __future__ import annotations

from fred_core.history.history_schema import TextPart
from fred_core.history.postgres_history_store import PostgresHistoryStore
from fred_sdk.contracts.runtime import SteeredUserMessageRuntimeEvent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage
from langgraph.config import get_stream_writer


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


class TurnSteeringMiddleware(AgentMiddleware):
    def __init__(
        self,
        session_id: str | None,
        pending_message_id: str | None = None,
        exchange_id: str | None = None,
    ) -> None:
        super().__init__()
        self._session_id = session_id
        self._pending_message_id = pending_message_id
        self._exchange_id = exchange_id
        self._first_boundary = True

    async def abefore_model(self, state, runtime) -> dict | None:
        if not self._session_id:
            return None
        history = turn_messages.require_history()
        pending = await history.pending_steered_messages(self._session_id)
        recoverable = (
            await history.recoverable_steered_messages(
                self._session_id, self._exchange_id
            )
            if self._first_boundary and self._exchange_id
            else []
        )
        self._first_boundary = False
        if not pending and not recoverable:
            return None
        seen_ids = {
            str(message.id)
            for message in state.get("messages", [])
            if getattr(message, "id", None)
        }
        injected = []
        for message, is_pending in [
            *((item, False) for item in recoverable),
            *((item, True) for item in pending),
        ]:
            extras = (message.metadata.model_extra or {}).get("extras")
            message_id = (
                extras.get("steered_message_id") if isinstance(extras, dict) else None
            )
            part = message.parts[0] if message.parts else None
            if not isinstance(message_id, str) or not isinstance(part, TextPart):
                continue
            content = part.text
            if message_id == self._pending_message_id:
                if not is_pending:
                    continue
            else:
                stable_id = f"steered:{message_id}"
                if stable_id not in seen_ids:
                    injected.append(
                        HumanMessage(
                            id=stable_id,
                            content="The user has sent an update while this task is in progress. "
                            "Apply this latest instruction before deciding what to do next; "
                            "it may add information, revise or cancel the earlier request. "
                            "If the user asks you to stop, do not call more tools; "
                            f"briefly acknowledge and end the turn.\n\n{content}",
                        )
                    )
            if is_pending:
                get_stream_writer()(
                    SteeredUserMessageRuntimeEvent(
                        message_id=message_id, content=content
                    )
                )
        return {"messages": injected} if injected else None
