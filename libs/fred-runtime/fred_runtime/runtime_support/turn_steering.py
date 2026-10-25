"""Process-local mailbox for the managed chat steering prototype."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from uuid import uuid4

from fred_sdk.contracts.runtime import SteeredUserMessageRuntimeEvent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage
from langgraph.config import get_stream_writer


@dataclass
class _ActiveTurn:
    token: str
    agent_instance_id: str
    user_id: str
    team_id: str
    pending: OrderedDict[str, str] = field(default_factory=OrderedDict)
    seen: set[str] = field(default_factory=set)
    active: bool = True


class TurnSteeringMailbox:
    def __init__(self) -> None:
        self._turns: dict[str, _ActiveTurn] = {}

    def start(
        self,
        session_id: str,
        agent_instance_id: str,
        user_id: str,
        team_id: str,
        *,
        resume: bool = False,
    ) -> str | None:
        current = self._turns.get(session_id)
        if current is not None:
            if current.active:
                return None
            if resume:
                if (
                    current.agent_instance_id != agent_instance_id
                    or current.user_id != user_id
                    or current.team_id != team_id
                ):
                    return None
                current.token = str(uuid4())
                current.active = True
                return current.token
            del self._turns[session_id]
        token = str(uuid4())
        self._turns[session_id] = _ActiveTurn(
            token, agent_instance_id, user_id, team_id
        )
        return token

    def end(self, session_id: str, token: str, *, paused: bool = False) -> None:
        current = self._turns.get(session_id)
        if current is not None and current.token == token:
            if paused and current.pending:
                current.active = False
            else:
                del self._turns[session_id]

    def offer(
        self,
        session_id: str,
        agent_instance_id: str,
        user_id: str,
        team_id: str,
        message_id: str,
        text: str,
    ) -> bool:
        current = self._turns.get(session_id)
        if (
            current is None
            or not current.active
            or current.agent_instance_id != agent_instance_id
            or current.user_id != user_id
            or current.team_id != team_id
        ):
            return False
        if message_id not in current.seen:
            current.pending[message_id] = text
            current.seen.add(message_id)
        return True

    def take(self, session_id: str) -> list[tuple[str, str]]:
        current = self._turns.get(session_id)
        if current is None or not current.active:
            return []
        messages = list(current.pending.items())
        current.pending.clear()
        return messages


turn_steering_mailbox = TurnSteeringMailbox()


class TurnSteeringMiddleware(AgentMiddleware):
    def __init__(self, session_id: str | None) -> None:
        super().__init__()
        self._session_id = session_id

    async def abefore_model(self, state, runtime) -> dict | None:
        if not self._session_id:
            return None
        messages = turn_steering_mailbox.take(self._session_id)
        if not messages:
            return None
        writer = get_stream_writer()
        for message_id, text in messages:
            writer(SteeredUserMessageRuntimeEvent(message_id=message_id, content=text))
        return {"messages": [HumanMessage(content=text) for _, text in messages]}
