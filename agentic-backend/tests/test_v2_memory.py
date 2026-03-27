"""
Tests for V2 agent multi-turn memory via SQL checkpointer.

Why these tests exist:
- V2 agents use LangGraph's SQL checkpointer as the sole source of agent memory.
- The history_store is for UI display only and must NOT be injected into LangGraph
  input when a checkpointer is active (doing so duplicates messages via add_messages).
- These tests guard against regressions where:
  a) the model does not receive prior conversation context on the second exchange, or
  b) _restore_history is incorrectly called for a V2 agent that has a checkpointer.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest
from fred_core import BaseSessionStore, KeycloakUser
from fred_core.common import PostgresStoreConfig
from fred_core.kpi import NoOpKPIWriter
from fred_core.sql import create_async_engine_from_config
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from agentic_backend.agents.v2 import BasicReActDefinition
from agentic_backend.core.agents.agent_factory import BaseAgentFactory
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.agents.v2 import (
    BoundRuntimeContext,
    ChatModelFactoryPort,
    PortableContext,
    PortableEnvironment,
    RuntimeServices,
)
from agentic_backend.core.agents.v2.react_runtime import ReActRuntime
from agentic_backend.core.agents.v2.session_agent import V2SessionAgent
from agentic_backend.core.agents.v2.sql_checkpointer import FredSqlCheckpointer
from agentic_backend.core.chatbot.chat_schema import (
    Channel,
    ChatMessage,
    ChatMetadata,
    Role,
    SessionSchema,
    TextPart,
)
from agentic_backend.core.chatbot.session_orchestrator import SessionOrchestrator
from agentic_backend.core.monitoring.noop_history_store import NoOpHistoryStore

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


_USER = KeycloakUser(
    uid="user-1",
    username="tester",
    email="t@example.com",
    roles=["viewer"],
)


class RecordingChatModel(BaseChatModel):
    """Fake chat model that records each instance's calls and returns responses.

    Why this exists:
    - Tests need a deterministic chat model that captures the exact message
      history passed into LangGraph across turns.

    How to use it:
    - Instantiate with a list of `responses`, then inspect `received` after
      invoking the runtime to assert which messages were provided to the model.
    """

    responses: list[str]
    received: list[list[BaseMessage]] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # type: ignore[override]
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.received.append(list(messages))
        idx = len(self.received) - 1
        text = self.responses[idx] if idx < len(self.responses) else "..."
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    @property
    def _llm_type(self) -> str:
        return "recording-fake"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {}


class StaticChatModelFactory(ChatModelFactoryPort):
    def __init__(self, model: BaseChatModel) -> None:
        self._model = model

    def build(self, definition: Any, binding: BoundRuntimeContext) -> BaseChatModel:  # type: ignore[override]
        return self._model


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

    async def save_with_conn(self, conn: Any, session: SessionSchema) -> None:
        await self.save(session)

    async def count_for_user(self, user_id: str) -> int:
        return len(await self.get_for_user(user_id))


class InMemoryHistoryStore(NoOpHistoryStore):
    def __init__(self) -> None:
        self.messages: dict[str, list[ChatMessage]] = {}
        self.get_call_count = 0

    async def save(
        self, session_id: str, messages: list[ChatMessage], user_id: str
    ) -> None:
        self.messages[session_id] = list(messages)

    async def get(self, session_id: str) -> list[ChatMessage]:
        self.get_call_count += 1
        return list(self.messages.get(session_id, []))

    async def save_with_conn(
        self, conn: Any, session_id: str, messages: list[ChatMessage], user_id: str
    ) -> None:
        await self.save(session_id, messages, user_id)


class CachedV2AgentFactory(BaseAgentFactory):
    """Returns the same agent instance on every call; reports is_cached=True
    from the second call onwards — matching real agent-cache behaviour."""

    def __init__(self, agent: V2SessionAgent) -> None:
        self._agent = agent
        self._first_call = True

    async def create_and_init(
        self,
        user: KeycloakUser,
        agent_id: str,
        runtime_context: RuntimeContext,
        session_id: str,
    ):
        self._agent.rebind(_binding(session_id, agent_id=agent_id))
        is_cached = not self._first_call
        self._first_call = False
        return self._agent, is_cached

    async def create_and_init_internal_profile(self, *args: Any, **kwargs: Any):
        raise NotImplementedError

    async def teardown_session_agents(self, session_id: str) -> None:
        pass

    def release_agent(self, session_id: str, agent_id: str) -> None:
        pass


def _binding(session_id: str, *, agent_id: str) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(session_id=session_id, user_id="user-1"),
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


def _minimal_config(enable_v2_sql_checkpointer: bool = True):
    from fred_core import M2MSecurity, SecurityConfiguration, UserSecurity
    from fred_core.common import (
        DuckdbStoreConfig,
        ModelConfiguration,
        PostgresStoreConfig,
    )
    from pydantic import AnyHttpUrl, AnyUrl

    from agentic_backend.common.structures import (
        AIConfig,
        AppConfig,
        Configuration,
        FrontendFlags,
        FrontendSettings,
        McpConfiguration,
        Properties,
        StorageConfig,
        TimeoutSettings,
    )

    duckdb = DuckdbStoreConfig(type="duckdb", duckdb_path="/tmp/test-v2-memory.db")
    return Configuration(
        app=AppConfig(
            base_url="/agentic/v1",
            address="127.0.0.1",
            port=8000,
            log_level="warning",
            reload=False,
            reload_dir=".",
            kpi_process_metrics_interval_sec=10,
        ),
        frontend_settings=FrontendSettings(
            feature_flags=FrontendFlags(
                enableK8Features=False, enableElecWarfare=False
            ),
            properties=Properties(
                logoName="fred", logoNameDark="fred-dark", siteDisplayName="Fred"
            ),
        ),
        security=SecurityConfiguration(
            m2m=M2MSecurity(
                enabled=False,
                realm_url=AnyUrl("http://localhost/realms/m2m"),
                client_id="c",
                audience="a",
            ),
            user=UserSecurity(
                enabled=False,
                realm_url=AnyUrl("http://localhost/realms/user"),
                client_id="c",
            ),
            authorized_origins=[AnyHttpUrl("http://localhost:5173")],
            rebac=None,
        ),
        mcp=McpConfiguration(servers=[]),
        storage=StorageConfig(
            postgres=PostgresStoreConfig(
                host="localhost", port=5432, username="u", database="d"
            ),
            agent_store=duckdb,
            session_store=duckdb,
            history_store=duckdb,
            feedback_store=duckdb,
            kpi_store=duckdb,
        ),
        ai=AIConfig(
            use_static_config_only=True,
            enable_catalog_mode=False,
            enable_v2_sql_checkpointer=enable_v2_sql_checkpointer,
            max_concurrent_agents=8,
            restore_max_exchanges=20,
            knowledge_flow_url="http://localhost:8000",
            timeout=TimeoutSettings(connect=5, read=15),
            max_concurrent_sessions_per_user=100,
            max_attached_files_per_user=10,
            max_attached_file_size_mb=10,
            default_chat_model=ModelConfiguration(
                provider="test",
                name="fake-model",
                settings={"temperature": 0.0},
            ),
        ),
    )


@asynccontextmanager
async def _fake_pg_tx():
    """Drop-in replacement for pg_async_tx() that uses no real DB connection."""
    yield MagicMock()


# ---------------------------------------------------------------------------
# Test 1 — multi-turn memory via SQL checkpointer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_v2_sql_checkpointer_provides_memory_across_exchanges(
    tmp_path,
) -> None:
    """
    On the second exchange the model must receive the full conversation context
    loaded from the SQL checkpointer — not just the latest message.

    Concretely: after "Hello!" → "First response.", the second LLM call
    must include both the first human message and the first assistant message,
    proving LangGraph restored prior state from the checkpoint.
    """
    session_id = "mem-test-session"
    engine = create_async_engine_from_config(
        PostgresStoreConfig(sqlite_path=str(tmp_path / "mem.db"))
    )
    try:
        model = RecordingChatModel(
            responses=["First response.", "Second response."],
            received=[],
        )
        definition = BasicReActDefinition(system_prompt_template="You are helpful.")
        checkpointer = FredSqlCheckpointer(engine)
        runtime = ReActRuntime(
            definition=definition,
            services=RuntimeServices(
                chat_model_factory=StaticChatModelFactory(model),
                checkpointer=checkpointer,
            ),
        )
        runtime.bind(_binding(session_id, agent_id=definition.agent_id))
        agent = V2SessionAgent(runtime=runtime)

        lc_config: dict = {"configurable": {"thread_id": session_id}}

        # First exchange
        async for _ in agent.astream_updates(
            state={"messages": [HumanMessage("Hello!")]},
            config=lc_config,
        ):
            pass

        # Second exchange — only the new message is passed; prior context must
        # come from the SQL checkpointer.
        async for _ in agent.astream_updates(
            state={"messages": [HumanMessage("What did I say?")]},
            config=lc_config,
        ):
            pass

        assert len(model.received) == 2, "model should have been called exactly twice"

        second_call_contents = " ".join(str(m.content) for m in model.received[1])

        assert "Hello!" in second_call_contents, (
            "Second LLM call must include the first user message from the checkpoint. "
            f"Got: {second_call_contents!r}"
        )
        assert "First response." in second_call_contents, (
            "Second LLM call must include the first assistant response from the checkpoint. "
            f"Got: {second_call_contents!r}"
        )
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Test 2 — history_store.get must not be called when a V2 checkpoint exists
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_v2_sql_checkpointer_history_store_not_read_when_checkpoint_exists(
    tmp_path,
) -> None:
    """
    When a V2 agent already has durable checkpoint state for its session,
    _restore_history must not read from history_store on either the first
    orchestrated exchange (is_cached=False) or later cached ones.

    Injecting restored messages alongside the checkpoint state would duplicate
    messages because add_messages deduplicates by ID, and messages reconstructed
    from history_store have new IDs different from those in the checkpoint.
    """
    session_id = "no-restore-session"
    engine = create_async_engine_from_config(
        PostgresStoreConfig(sqlite_path=str(tmp_path / "no-restore.db"))
    )
    try:
        model = RecordingChatModel(
            responses=["Response 1.", "Response 2."],
            received=[],
        )
        definition = BasicReActDefinition(system_prompt_template="You are helpful.")
        checkpointer = FredSqlCheckpointer(engine)
        runtime = ReActRuntime(
            definition=definition,
            services=RuntimeServices(
                chat_model_factory=StaticChatModelFactory(model),
                checkpointer=checkpointer,
            ),
        )
        runtime.bind(_binding(session_id, agent_id=definition.agent_id))
        agent = V2SessionAgent(runtime=runtime)
        lc_config: dict[str, dict[str, str]] = {
            "configurable": {"thread_id": session_id}
        }

        async for _ in agent.astream_updates(
            state={"messages": [HumanMessage("Checkpoint seed")]},
            config=lc_config,
        ):
            pass

        session_store = InMemorySessionStore()
        history_store = InMemoryHistoryStore()
        session = SessionSchema(
            id=session_id,
            user_id="user-1",
            agent_id=definition.agent_id,
            title="No restore test",
            updated_at=_utcnow(),
            next_rank=0,  # pre-seeded so _ensure_next_rank skips history_store.get
        )
        await session_store.save(session)

        orchestrator = SessionOrchestrator(
            configuration=_minimal_config(enable_v2_sql_checkpointer=True),
            session_store=session_store,
            attachments_store=None,
            agent_factory=CachedV2AgentFactory(agent),
            agent_manager=MagicMock(),
            history_store=history_store,
            kpi=NoOpKPIWriter(),
        )

        runtime_ctx = RuntimeContext(session_id=session_id, user_id="user-1")

        async def _noop_cb(event: dict) -> None:
            pass

        # Patch pg_async_tx so the persist path works without a real Postgres connection.
        with patch(
            "agentic_backend.core.chatbot.session_orchestrator.pg_async_tx",
            _fake_pg_tx,
        ):
            # First exchange: CachedV2AgentFactory reports is_cached=False
            await orchestrator.chat_ask_websocket(
                user=_USER,
                callback=_noop_cb,
                session_id=session_id,
                message="First message",
                agent_id=definition.agent_id,
                runtime_context=runtime_ctx,
            )
            reads_after_first = history_store.get_call_count

            # Second exchange: CachedV2AgentFactory reports is_cached=True
            await orchestrator.chat_ask_websocket(
                user=_USER,
                callback=_noop_cb,
                session_id=session_id,
                message="Second message",
                agent_id=definition.agent_id,
                runtime_context=runtime_ctx,
            )
            reads_after_second = history_store.get_call_count

        assert reads_after_first == 0, (
            "history_store.get must not be called when a V2 SQL checkpoint "
            f"already exists (first exchange). Got {reads_after_first} call(s)."
        )
        assert reads_after_second == 0, (
            "history_store.get must not be called when a V2 SQL checkpoint "
            f"already exists (second/cached exchange). Got {reads_after_second} call(s)."
        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_v2_sql_checkpointer_restores_history_once_when_checkpoint_missing(
    tmp_path,
) -> None:
    """
    A migrated V2 session can have persisted chat history before any SQL
    checkpoint exists for its thread.

    In that case the first cache miss must restore history exactly once to seed
    the durable checkpoint; later exchanges must stop reading history_store and
    rely on the checkpoint instead.
    """
    session_id = "restore-once-session"
    engine = create_async_engine_from_config(
        PostgresStoreConfig(sqlite_path=str(tmp_path / "restore-once.db"))
    )
    try:
        model = RecordingChatModel(
            responses=["Migrated response 1.", "Migrated response 2."],
            received=[],
        )
        definition = BasicReActDefinition(system_prompt_template="You are helpful.")
        checkpointer = FredSqlCheckpointer(engine)
        runtime = ReActRuntime(
            definition=definition,
            services=RuntimeServices(
                chat_model_factory=StaticChatModelFactory(model),
                checkpointer=checkpointer,
            ),
        )
        runtime.bind(_binding(session_id, agent_id=definition.agent_id))
        agent = V2SessionAgent(runtime=runtime)

        session_store = InMemorySessionStore()
        history_store = InMemoryHistoryStore()
        history_store.messages[session_id] = [
            ChatMessage(
                session_id=session_id,
                exchange_id="legacy-exchange",
                rank=0,
                timestamp=_utcnow(),
                role=Role.user,
                channel=Channel.final,
                parts=[TextPart(text="Legacy hello")],
                metadata=ChatMetadata(agent_id=definition.agent_id),
            ),
            ChatMessage(
                session_id=session_id,
                exchange_id="legacy-exchange",
                rank=1,
                timestamp=_utcnow(),
                role=Role.assistant,
                channel=Channel.final,
                parts=[TextPart(text="Legacy reply")],
                metadata=ChatMetadata(agent_id=definition.agent_id),
            ),
        ]
        session = SessionSchema(
            id=session_id,
            user_id="user-1",
            agent_id=definition.agent_id,
            title="Restore once test",
            updated_at=_utcnow(),
            next_rank=2,
        )
        await session_store.save(session)

        orchestrator = SessionOrchestrator(
            configuration=_minimal_config(enable_v2_sql_checkpointer=True),
            session_store=session_store,
            attachments_store=None,
            agent_factory=CachedV2AgentFactory(agent),
            agent_manager=MagicMock(),
            history_store=history_store,
            kpi=NoOpKPIWriter(),
        )

        runtime_ctx = RuntimeContext(session_id=session_id, user_id="user-1")

        async def _noop_cb(event: dict) -> None:
            pass

        with patch(
            "agentic_backend.core.chatbot.session_orchestrator.pg_async_tx",
            _fake_pg_tx,
        ):
            await orchestrator.chat_ask_websocket(
                user=_USER,
                callback=_noop_cb,
                session_id=session_id,
                message="First migrated question",
                agent_id=definition.agent_id,
                runtime_context=runtime_ctx,
            )
            reads_after_first = history_store.get_call_count

            await orchestrator.chat_ask_websocket(
                user=_USER,
                callback=_noop_cb,
                session_id=session_id,
                message="Second migrated question",
                agent_id=definition.agent_id,
                runtime_context=runtime_ctx,
            )
            reads_after_second = history_store.get_call_count

        first_call_contents = " ".join(str(m.content) for m in model.received[0])
        second_call_contents = " ".join(str(m.content) for m in model.received[1])

        assert reads_after_first == 1, (
            "The first cache-miss exchange should restore history exactly once "
            "when the durable checkpoint thread is still empty."
        )
        assert reads_after_second == 1, (
            "Later exchanges should stop reading history_store once the SQL "
            "checkpointer has been seeded."
        )
        assert "Legacy hello" in first_call_contents
        assert "Legacy reply" in first_call_contents
        assert "Migrated response 1." in second_call_contents
    finally:
        await engine.dispose()
