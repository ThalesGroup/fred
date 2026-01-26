"""
Utilities for building a consistent LangGraph MessagesState regardless of runtime path.

Both the WebSocket orchestrator and the Temporal runner should rely on these helpers so
each agent always receives the same kind of state regardless of how it was invoked.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence, cast

from fred_core.scheduler import AgentConversationPayload
from langchain_core.messages import AnyMessage, BaseMessage, HumanMessage
from langgraph.graph import MessagesState


def build_messages_state(
    *,
    messages: Sequence[AnyMessage] | None = None,
    question: str | None = None,
    payload: Mapping[str, Any] | None = None,
) -> MessagesState:
    """
    Return a MessagesState where the `messages` key always exists and ends with the human
    question. Priority: explicit messages > payload messages > payload question.
    """
    conversation = build_agent_conversation_payload(
        messages=messages, question=question, payload=payload
    )
    if conversation.messages:
        return {"messages": list(conversation.messages)}
    assert conversation.question is not None
    return {"messages": [HumanMessage(conversation.question)]}


def build_agent_conversation_payload(
    *,
    messages: Sequence[AnyMessage] | None = None,
    question: str | None = None,
    payload: Mapping[str, Any] | None = None,
) -> AgentConversationPayload:
    """
    Build a shared conversation payload that either carries an explicit question or
    a sequence of LangChain messages so both websocket and Temporal paths use the
    same seed.
    """
    resolved_messages: list[AnyMessage] | None = None
    if messages:
        resolved_messages = list(messages)
    else:
        resolved_messages = _extract_messages_from_payload(payload)

    resolved_question = _resolve_question(question=question, payload=payload)

    if resolved_messages:
        return AgentConversationPayload(messages=resolved_messages)
    if resolved_question:
        return AgentConversationPayload(question=resolved_question)
    raise ValueError(
        "Cannot build AgentConversationPayload: missing question and no fallback messages."
    )


def _resolve_question(
    *,
    question: str | None,
    payload: Mapping[str, Any] | None,
) -> str | None:
    if question and question.strip():
        return question.strip()

    if not payload:
        return None

    candidate = payload.get("question")
    resolved = _extract_text_candidate(candidate)
    if resolved:
        return resolved

    candidate = payload.get("message")
    return _extract_text_candidate(candidate)


def _extract_text_candidate(candidate: Any) -> str | None:
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    if isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes)):
        for item in reversed(candidate):
            resolved = _extract_text_candidate(item)
            if resolved:
                return resolved
    if isinstance(candidate, Mapping):
        content = candidate.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    return None


def _extract_messages_from_payload(
    payload: Mapping[str, Any] | None,
) -> list[AnyMessage] | None:
    if not payload:
        return None

    raw = payload.get("messages")
    if not raw or isinstance(raw, (str, bytes)):
        return None

    if isinstance(raw, Sequence):
        normalized: list[AnyMessage] = []
        for item in raw:
            if isinstance(item, BaseMessage):
                normalized.append(cast(AnyMessage, item))
            elif isinstance(item, str):
                normalized.append(HumanMessage(item))
            elif isinstance(item, Mapping):
                content = item.get("content")
                if isinstance(content, str):
                    normalized.append(HumanMessage(content))
                else:
                    normalized.append(HumanMessage(str(item)))
            else:
                normalized.append(HumanMessage(str(item)))
        if normalized:
            return normalized

    return None
