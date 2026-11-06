"""Deliver durable in-thread user updates at safe model boundaries."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fred_core.history.history_schema import TextPart
from fred_core.history.postgres_history_store import (
    PostgresHistoryStore,
    steered_reply_id,
)
from fred_sdk.contracts.runtime import (
    SteeredAssistantMessageRuntimeEvent,
    SteeredUserMessageDelivery,
    SteeredUserMessageRuntimeEvent,
)
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.messages.ai import InputTokenDetails, UsageMetadata
from langgraph.config import get_stream_writer

from fred_runtime.runtime_support.model_metadata import (
    runtime_metadata_from_message,
    sum_token_usage,
)
from fred_runtime.runtime_support.run_scope import RunScope
from fred_runtime.support.thinking import content_to_text

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


def _continue_after_steered_reply(request: ModelRequest) -> ModelRequest:
    # Keep the visible reply in context while ending the request on a user role.
    # Mistral rejects a completed assistant message as the final input.
    return request.override(
        messages=[
            *request.messages,
            HumanMessage(
                content=(
                    "Continue the original task unless the latest user update changes "
                    "or stops it. The brief reply above was already shown to the user; "
                    "do not repeat it."
                )
            ),
        ]
    )


class TurnSteeringMiddleware(AgentMiddleware):
    def __init__(
        self,
        session_id: str | None,
        pending_message_id: str | None = None,
        exchange_id: str | None = None,
        language: str | None = None,
    ) -> None:
        super().__init__()
        self._session_id = session_id
        self._pending_message_id = pending_message_id
        self._exchange_id = exchange_id
        self._language = language
        self._first_boundary = True
        self._unanswered_ids: tuple[str, ...] = ()
        self._pending_delivery: tuple[tuple[str, str], ...] = ()

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
        replies = (
            await history.steered_assistant_messages(
                self._session_id, self._exchange_id
            )
            if self._first_boundary and self._exchange_id
            else []
        )
        self._first_boundary = False
        if not pending and not recoverable and not replies:
            self._unanswered_ids = ()
            self._pending_delivery = ()
            return None
        seen_ids = {
            str(message.id)
            for message in state.get("messages", [])
            if getattr(message, "id", None)
        }
        injected: list[tuple[int, AIMessage | HumanMessage]] = []
        answered_ids: set[str] = set()
        for reply in replies:
            extras = (reply.metadata.model_extra or {}).get("extras")
            reply_for = (
                extras.get("steered_reply_for") if isinstance(extras, dict) else None
            )
            if isinstance(reply_for, list):
                answered_ids.update(item for item in reply_for if isinstance(item, str))
            part = reply.parts[0] if reply.parts else None
            if isinstance(part, TextPart):
                reply_id = steered_reply_id(tuple(reply_for)) if reply_for else None
                if reply_id and reply_id not in seen_ids:
                    injected.append(
                        (
                            reply.rank,
                            AIMessage(
                                id=reply_id,
                                content=part.text,
                                additional_kwargs={"steered_reply_for": reply_for},
                            ),
                        )
                    )
        unanswered: list[str] = []
        pending_delivery: list[tuple[str, str]] = []
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
                        (
                            message.rank,
                            HumanMessage(
                                id=stable_id,
                                content="The user has sent an update while this task is in progress. "
                                "Apply this latest instruction before deciding what to do next; "
                                "it may add information, revise or cancel the earlier request. "
                                "If the user asks you to stop, do not call more tools; "
                                f"briefly acknowledge and end the turn.\n\n{content}",
                            ),
                        )
                    )
                if message_id not in answered_ids:
                    unanswered.append(message_id)
            if is_pending:
                if message_id == self._pending_message_id:
                    get_stream_writer()(
                        SteeredUserMessageRuntimeEvent(
                            message_id=message_id, content=content
                        )
                    )
                else:
                    pending_delivery.append((message_id, content))
        self._unanswered_ids = tuple(unanswered)
        self._pending_delivery = tuple(pending_delivery)
        injected.sort(key=lambda item: (0, item[0]) if item[0] >= 0 else (1, -item[0]))
        return {"messages": [item for _, item in injected]} if injected else None

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        message_ids = self._unanswered_ids
        self._unanswered_ids = ()
        pending_delivery = self._pending_delivery
        self._pending_delivery = ()
        if not message_ids:
            if request.messages and isinstance(request.messages[-1], AIMessage):
                reply_for = request.messages[-1].additional_kwargs.get(
                    "steered_reply_for"
                )
                if isinstance(reply_for, list) and reply_for:
                    request = _continue_after_steered_reply(request)
            return await handler(request)

        writer = get_stream_writer()
        writer({"kind": "_steered_reply_start"})
        instruction = SystemMessage(
            content=(
                f"{request.system_prompt or ''}\n\n"
                "Reply directly and briefly to every newly received in-progress update "
                "in order, using one concise assistant message. "
                "If it asks for status, explain the actual progress from the conversation "
                "and tool results; do not claim unfinished work is done. "
                "If it changes the task, acknowledge the change. "
                "This is a visible assistant message before work resumes. "
                "Do not call tools or give a final answer to the original task."
            )
        )
        reply_request = request.override(
            tools=[],
            tool_choice="none",
            response_format=None,
            system_message=instruction,
        )
        reply: AIMessage | None = None
        reply_usage: dict[str, int] | None = None
        for attempt in range(2):
            interim = await handler(reply_request)
            candidate = next(
                (
                    message
                    for message in interim.result
                    if isinstance(message, AIMessage)
                ),
                None,
            )
            if candidate is not None:
                _, usage, _ = runtime_metadata_from_message(candidate)
                reply_usage = sum_token_usage(reply_usage, usage)
            if candidate is not None and not candidate.tool_calls:
                visible_text = content_to_text(candidate.content).strip()
                if visible_text:
                    reply = candidate
                    break
            logger.warning(
                "event=steered_reply_invalid attempt=%d reason=%s",
                attempt + 1,
                "missing_assistant"
                if candidate is None
                else "unexpected_tool_calls"
                if candidate.tool_calls
                else "empty_visible_text",
            )
            reply_request = reply_request.override(
                system_message=SystemMessage(
                    content=(
                        f"{request.system_prompt or ''}\n\n"
                        "Reply briefly in plain visible text to the latest user update. "
                        "Do not call tools. The user is waiting for this reply."
                    )
                )
            )
        if reply is None:
            french = (self._language or "").lower().startswith("fr")
            reply = AIMessage(
                content=(
                    (
                        "Je n'ai pas pu répondre immédiatement à tes messages. "
                        "Je les ai pris en compte."
                        if len(message_ids) > 1
                        else "Je n'ai pas pu répondre immédiatement à ton message. "
                        "Je l'ai pris en compte."
                    )
                    if french
                    else (
                        "I could not answer your updates immediately. "
                        "I have taken them into account."
                        if len(message_ids) > 1
                        else "I could not answer your update immediately. "
                        "I have taken it into account."
                    )
                )
            )
        if reply_usage is not None:
            reply.usage_metadata = UsageMetadata(
                input_tokens=reply_usage["input_tokens"],
                output_tokens=reply_usage["output_tokens"],
                total_tokens=reply_usage["total_tokens"],
                input_token_details=InputTokenDetails(
                    cache_read=reply_usage["cache_read_tokens"],
                    cache_creation=reply_usage["cache_creation_tokens"],
                ),
            )
        reply.id = steered_reply_id(message_ids)
        reply.additional_kwargs["steered_reply_for"] = list(message_ids)
        scope = RunScope.current()
        if scope is None:
            raise RuntimeError("Steered reply has no active run scope")
        reply_id = steered_reply_id(message_ids)
        receipt = scope.register_event_receipt(reply_id)
        try:
            writer(
                SteeredAssistantMessageRuntimeEvent(
                    message_ids=message_ids,
                    content=content_to_text(reply.content),
                    deliveries=tuple(
                        SteeredUserMessageDelivery(
                            message_id=message_id, content=content
                        )
                        for message_id, content in pending_delivery
                    ),
                )
            )
            persisted = await receipt
        finally:
            scope.discard_event_receipt(reply_id)
        reply.content = persisted["content"]
        continued = await handler(
            _continue_after_steered_reply(
                request.override(messages=[*request.messages, reply])
            )
        )
        return ModelResponse(
            result=[reply, *continued.result],
            structured_response=continued.structured_response,
        )
