from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fred_core import KeycloakUser, PostgresStoreConfig
from fred_core.kpi import NoOpKPIWriter
from fred_core.sql import create_async_engine_from_config
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel

from agentic_backend.agents.v2 import BasicReActDefinition
from agentic_backend.common.structures import Configuration
from agentic_backend.core.agents.agent_factory import BaseAgentFactory
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.agents.v2 import (
    BoundRuntimeContext,
    ChatModelFactoryPort,
    ExecutionConfig,
    PortableContext,
    PortableEnvironment,
    RuntimeServices,
    ToolProviderPort,
)
from agentic_backend.core.agents.v2.react_runtime import (
    ReActInput,
    ReActMessage,
    ReActMessageRole,
    ReActRuntime,
)
from agentic_backend.core.agents.v2.runtime import AwaitingHumanRuntimeEvent
from agentic_backend.core.agents.v2.session_agent import V2SessionAgent
from agentic_backend.core.agents.v2.sql_checkpointer import FredSqlCheckpointer
from agentic_backend.core.chatbot.chat_schema import ChatMessage, SessionSchema
from agentic_backend.core.chatbot.session_orchestrator import SessionOrchestrator
from agentic_backend.core.monitoring.noop_history_store import NoOpHistoryStore
from agentic_backend.core.session.stores.base_session_store import BaseSessionStore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


class ToolFriendlyFakeChatModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # type: ignore[override]
        return self


class StaticChatModelFactory(ChatModelFactoryPort):
    def __init__(self, model: ToolFriendlyFakeChatModel) -> None:
        self.model = model

    def build(self, definition, binding: BoundRuntimeContext):  # type: ignore[override]
        return self.model


class ApprovalToolProvider(ToolProviderPort):
    def bind(self, binding: BoundRuntimeContext) -> None:
        return None

    async def activate(self) -> None:
        return None

    def get_tools(self) -> tuple[BaseTool, ...]:
        class _Args(BaseModel):
            ticket_id: str

        async def _update_ticket(ticket_id: str) -> str:
            return f"ticket {ticket_id} updated"

        return (
            StructuredTool.from_function(
                func=None,
                coroutine=_update_ticket,
                name="update_ticket",
                description="Update an incident ticket.",
                args_schema=_Args,
            ),
        )

    async def aclose(self) -> None:
        return None


class InMemorySessionStore(BaseSessionStore):
    def __init__(self) -> None:
        self.sessions: dict[str, SessionSchema] = {}

    async def save(self, session: SessionSchema) -> None:
        self.sessions[session.id] = session

    async def get(self, session_id: str) -> SessionSchema | None:
        return self.sessions.get(session_id)

    async def delete(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)

    async def get_for_user(self, user_id: str) -> list[SessionSchema]:
        return [s for s in self.sessions.values() if s.user_id == user_id]

    async def save_with_conn(self, conn, session: SessionSchema) -> None:
        await self.save(session)

    async def count_for_user(self, user_id: str) -> int:
        return len(await self.get_for_user(user_id))


class InMemoryHistoryStore(NoOpHistoryStore):
    def __init__(self) -> None:
        self.messages: dict[str, list[ChatMessage]] = {}

    async def save(
        self, session_id: str, messages: list[ChatMessage], user_id: str
    ) -> None:
        self.messages[session_id] = list(messages)

    async def get(self, session_id: str) -> list[ChatMessage]:
        return list(self.messages.get(session_id, []))

    async def save_with_conn(
        self, conn, session_id: str, messages: list[ChatMessage], user_id: str
    ) -> None:
        await self.save(session_id, messages, user_id)


class FreshV2AgentFactory(BaseAgentFactory):
    def __init__(self, agent: V2SessionAgent) -> None:
        self.agent = agent

    async def create_and_init(
        self,
        user: KeycloakUser,
        agent_id: str,
        runtime_context: RuntimeContext,
        session_id: str,
    ):
        self.agent.rebind(_binding(session_id, agent_id=agent_id))
        return self.agent, False

    async def create_and_init_internal_profile(
        self,
        user: KeycloakUser,
        profile_id: str,
        runtime_context: RuntimeContext,
        session_id: str,
    ):
        raise NotImplementedError

    async def teardown_session_agents(self, session_id: str) -> None:
        return None

    def release_agent(self, session_id: str, agent_id: str) -> None:
        return None


def _binding(session_id: str, *, agent_id: str) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(
            session_id=session_id,
            user_id="user-1",
            language="en-US",
        ),
        portable_context=PortableContext(
            request_id=f"req-{session_id}",
            correlation_id=f"corr-{session_id}",
            actor="user:demo",
            tenant="fred",
            environment=PortableEnvironment.DEV,
            session_id=session_id,
            agent_id=agent_id,
        ),
    )


def _user_input(text: str) -> ReActInput:
    return ReActInput(
        messages=(ReActMessage(role=ReActMessageRole.USER, content=text),)
    )


def _build_runtime(
    *,
    model: ToolFriendlyFakeChatModel,
    checkpointer: FredSqlCheckpointer,
    session_id: str,
) -> ReActRuntime:
    definition = BasicReActDefinition(enable_tool_approval=True)
    runtime = ReActRuntime(
        definition=definition,
        services=RuntimeServices(
            chat_model_factory=StaticChatModelFactory(model),
            tool_provider=ApprovalToolProvider(),
            checkpointer=checkpointer,
        ),
    )
    runtime.bind(_binding(session_id, agent_id=definition.agent_id))
    return runtime


@pytest.mark.asyncio
async def test_v2_react_resume_survives_backend_restart_without_agent_cache(
    minimal_generalist_config: Configuration, tmp_path
) -> None:
    session_id = "resume-sql-session"
    exchange_id = "exchange-resume-1"
    sqlite_path = tmp_path / "resume-v2.db"
    engine = create_async_engine_from_config(
        PostgresStoreConfig(sqlite_path=str(sqlite_path))
    )

    try:
        first_runtime = _build_runtime(
            model=ToolFriendlyFakeChatModel(
                responses=[
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "id": "call-approval-sql-1",
                                "name": "update_ticket",
                                "args": {"ticket_id": "INC-42"},
                            }
                        ],
                    )
                ]
            ),
            checkpointer=FredSqlCheckpointer(engine),
            session_id=session_id,
        )
        first_executor = await first_runtime.get_executor()
        first_pass_events = [
            event
            async for event in first_executor.stream(
                _user_input("Update the incident."),
                ExecutionConfig(thread_id=session_id),
            )
        ]
        awaiting_human = first_pass_events[-1]
        assert isinstance(awaiting_human, AwaitingHumanRuntimeEvent)
        checkpoint_id = awaiting_human.request.checkpoint_id
        assert checkpoint_id is not None

        second_runtime = _build_runtime(
            model=ToolFriendlyFakeChatModel(
                responses=[AIMessage(content="The ticket was updated.")]
            ),
            checkpointer=FredSqlCheckpointer(engine),
            session_id=session_id,
        )
        agent = V2SessionAgent(runtime=second_runtime)

        session_store = InMemorySessionStore()
        history_store = InMemoryHistoryStore()
        session = SessionSchema(
            id=session_id,
            user_id="user-1",
            agent_id=second_runtime.definition.agent_id,
            title="Resume Test",
            updated_at=_utcnow(),
        )
        await session_store.save(session)

        orchestrator = SessionOrchestrator(
            configuration=minimal_generalist_config,
            session_store=session_store,
            attachments_store=None,
            agent_factory=FreshV2AgentFactory(agent),
            agent_manager=MagicMock(),
            history_store=history_store,
            kpi=NoOpKPIWriter(),
        )

        emitted: list[dict] = []

        async def _callback(event: dict) -> None:
            emitted.append(event)

        user = KeycloakUser(
            uid="user-1",
            username="tester",
            email="t@example.com",
            roles=["viewer"],
        )

        updated_session, messages = await orchestrator.resume_interrupted_exchange(
            user=user,
            callback=_callback,
            session_id=session_id,
            exchange_id=exchange_id,
            agent_id=second_runtime.definition.agent_id,
            resume_payload={
                "checkpoint_id": checkpoint_id,
                "choice_id": "proceed",
            },
            runtime_context=RuntimeContext(session_id=session_id, user_id="user-1"),
        )

        assert updated_session.id == session_id
        assert any(message.role.value == "assistant" for message in messages)
        assert any(
            "The ticket was updated." in str(part.get("text", ""))
            for event in emitted
            for part in event.get("parts", [])
            if isinstance(part, dict)
        )
    finally:
        await engine.dispose()
