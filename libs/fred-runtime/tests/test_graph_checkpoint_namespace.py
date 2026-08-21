import pytest

from fred_runtime.graph.graph_runtime import GraphRuntime
from fred_runtime.runtime_support.sql_checkpointer import FredSqlCheckpointer
from fred_sdk.contracts.runtime import ExecutionConfig, RuntimeServices
from sqlalchemy.ext.asyncio import create_async_engine
from collections.abc import Mapping

from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import (
    GraphAgentDefinition,
    GraphDefinition,
    GraphNodeDefinition,
)
from fred_sdk.graph.runtime import GraphNodeResult
from pydantic import BaseModel


class _Input(BaseModel):
    message: str = ""


class _State(BaseModel):
    remembered: str = ""


class _GraphAgent(GraphAgentDefinition):
    agent_id: str = "test.graph.memory"

    role: str = "test"
    description: str = "test"

    def build_graph(self) -> GraphDefinition:
        return GraphDefinition(
            state_model_name="State",
            entry_node="n",
            nodes=(GraphNodeDefinition(node_id="n", title="N"),),
        )

    def input_model(self) -> type[BaseModel]:
        return _Input

    def state_model(self) -> type[BaseModel]:
        return _State

    def output_model(self) -> type[BaseModel]:
        return _Input

    def _turn_carry_fields(self) -> frozenset[str]:
        return frozenset({"remembered"})

    def build_initial_state(
        self,
        input_model: BaseModel,
        binding: BoundRuntimeContext,
    ) -> BaseModel:
        del binding
        return _State(remembered=getattr(input_model, "message", ""))

    def node_handlers(self) -> Mapping[str, object]:
        async def _n(state: BaseModel, ctx: object) -> GraphNodeResult:
            del state, ctx
            return GraphNodeResult()

        return {"n": _n}

    def build_output(self, state: BaseModel) -> BaseModel:
        return _Input(message=getattr(state, "remembered", ""))


def _binding(*, agent_instance_id: str | None = None) -> BoundRuntimeContext:
    baggage = {}
    if agent_instance_id is not None:
        baggage["agent_instance_id"] = agent_instance_id

    return BoundRuntimeContext(
        runtime_context=RuntimeContext(
            session_id="shared-session",
            user_id="u",
            team_id="t",
        ),
        portable_context=PortableContext(
            request_id="r",
            correlation_id="c",
            actor="u",
            tenant="t",
            environment=PortableEnvironment.DEV,
            session_id="shared-session",
            user_id="u",
            team_id="t",
            baggage=baggage,
        ),
    )

@pytest.mark.asyncio
async def test_graph_agents_with_same_session_do_not_share_completed_state(tmp_path) -> None:
    db = tmp_path / "graph-memory.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db}")

    try:
        checkpointer = FredSqlCheckpointer(engine, prefix="v2_")
        await checkpointer._ensure_tables()

        services = RuntimeServices(checkpointer=checkpointer)

        agent_a = _GraphAgent(agent_id="test.graph.memory.a")
        runtime_a = GraphRuntime(definition=agent_a, services=services)
        executor_a = await runtime_a.build_executor(_binding())

        result_a = await executor_a.invoke(
            _Input(message="from-a"),
            ExecutionConfig(session_id="shared-session"),
        )
        assert result_a.message == "from-a"

        agent_b = _GraphAgent(agent_id="test.graph.memory.b")
        runtime_b = GraphRuntime(definition=agent_b, services=services)
        executor_b = await runtime_b.build_executor(_binding())

        result_b = await executor_b.invoke(
            _Input(message="from-b"),
            ExecutionConfig(session_id="shared-session"),
        )

        assert result_b.message == "from-b"
    finally:
        await engine.dispose()

@pytest.mark.asyncio
async def test_graph_managed_instances_with_same_agent_and_session_do_not_share_state(
    tmp_path,
) -> None:
    db = tmp_path / "graph-managed-memory.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db}")

    try:
        checkpointer = FredSqlCheckpointer(engine, prefix="v2_")
        await checkpointer._ensure_tables()

        services = RuntimeServices(checkpointer=checkpointer)
        definition = _GraphAgent(agent_id="test.graph.memory")

        runtime_a = GraphRuntime(definition=definition, services=services)
        executor_a = await runtime_a.build_executor(
            _binding(agent_instance_id="instance-a")
        )

        result_a = await executor_a.invoke(
            _Input(message="from-instance-a"),
            ExecutionConfig(session_id="shared-session"),
        )
        assert result_a.message == "from-instance-a"

        runtime_b = GraphRuntime(definition=definition, services=services)
        executor_b = await runtime_b.build_executor(
            _binding(agent_instance_id="instance-b")
        )

        result_b = await executor_b.invoke(
            _Input(message="from-instance-b"),
            ExecutionConfig(session_id="shared-session"),
        )

        assert result_b.message == "from-instance-b"
    finally:
        await engine.dispose()

@pytest.mark.asyncio
async def test_graph_same_agent_and_session_preserves_its_own_completed_state(
    tmp_path,
) -> None:
    db = tmp_path / "graph-own-memory.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db}")

    try:
        checkpointer = FredSqlCheckpointer(engine, prefix="v2_")
        await checkpointer._ensure_tables()

        services = RuntimeServices(checkpointer=checkpointer)
        definition = _GraphAgent(agent_id="test.graph.memory")

        runtime_first = GraphRuntime(definition=definition, services=services)
        executor_first = await runtime_first.build_executor(_binding())

        result_first = await executor_first.invoke(
            _Input(message="remember-me"),
            ExecutionConfig(session_id="shared-session"),
        )
        assert result_first.message == "remember-me"

        runtime_second = GraphRuntime(definition=definition, services=services)
        executor_second = await runtime_second.build_executor(_binding())

        result_second = await executor_second.invoke(
            _Input(message="new-input"),
            ExecutionConfig(session_id="shared-session"),
        )

        assert result_second.message == "remember-me"
    finally:
        await engine.dispose()