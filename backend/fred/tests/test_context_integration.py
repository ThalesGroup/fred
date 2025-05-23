# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import tempfile
import pathlib
from datetime import datetime
import pytest
from unittest.mock import Mock, patch, AsyncMock

from flow import AgentFlow
from context.context_service import ContextService
from fred.services.chatbot_session.in_memory_session_backend import InMemorySessionStorage
from services.chatbot_session.session_manager import SessionManager
from services.chatbot_session.structure.chat_schema import SessionSchema
from chatbot.agent_manager import AgentManager
from langchain_core.messages import AIMessage, SystemMessage


@pytest.fixture
def context_dir():
    with tempfile.TemporaryDirectory() as tmp:
        yield pathlib.Path(tmp)


@pytest.fixture
def context_service(context_dir):
    return ContextService(minio_client=None, local_base_dir=context_dir)


@pytest.fixture
def mock_model():
    model = AsyncMock()
    model.ainvoke.return_value = AIMessage(
        content="Response with context",
        response_metadata={"model_name": "test-model", "sources": []}
    )
    return model


@pytest.fixture
def test_agent(mock_model):
    graph_mock = Mock()
    compiled_graph = Mock()
    graph_mock.compile.return_value = compiled_graph

    agent = AgentFlow(
        name="test-agent",
        role="Test Agent",
        nickname="Tester",
        description="Agent for testing context integration",
        icon="test-icon",
        graph=graph_mock,
        base_prompt="I am a test agent without context",
        categories=["test"],
        tag="test"
    )

    async def mock_expert(state):
        prompt = SystemMessage(content=agent.base_prompt)
        return {"messages": [await mock_model.ainvoke([prompt] + state["messages"])]}

    agent.expert = mock_expert
    return agent


@pytest.fixture
def session_manager(context_service, test_agent):
    mock_agent_manager = Mock(spec=AgentManager)
    mock_agent_manager.get_create_agent_instance.return_value = test_agent

    with patch("services.chatbot_session.session_manager.get_context_service", return_value=context_service):
        manager = SessionManager(storage=InMemorySessionStorage(), agent_manager=mock_agent_manager)

        async def mock_stream(compiled_graph, input_messages, session_id, callback, assistant_id, config=None):
            # Simulate a streamed message
            await callback({
                "content": "Streaming reply",
                "type": "ai",
                "session_id": session_id
            })

            # Simulate final messages
            final_msg = AIMessage(
                content="Final reply with context",
                response_metadata={"model_name": "test-model", "sources": []}
            )

            all_messages = [
                SystemMessage(content="Intermediate system thought"),
                final_msg
            ]
            # Simulate returned list of messages
            return [
                SystemMessage(content="Intermediate system thought"),
                AIMessage(
                    content="Final reply with context",
                    response_metadata={"model_name": "test-model", "sources": []}
                )
            ]

        manager._stream_agent_response = mock_stream
        return manager


def test_save_and_retrieve_context(context_service, context_dir):
    context1 = {"title": "Test Context 1", "content": "This is test context 1"}
    context2 = {"title": "Test Context 2", "content": "This is test context 2"}

    context_service.save_context("test-agent", context1)
    context_service.save_context("test-agent", context2)

    contexts = context_service.get_contexts("test-agent")
    assert len(contexts) == 2
    assert contexts[0]["title"] == "Test Context 1"
    assert contexts[1]["title"] == "Test Context 2"

    context_file = context_dir / "test-agent_contexts.json"
    assert context_file.exists()

    with open(context_file, 'r') as f:
        saved_data = json.load(f)
        assert len(saved_data) == 2


@pytest.mark.asyncio
async def test_session_manager_with_context_enrichment(session_manager, context_service):
    context_service.save_context("test-agent", {
        "title": "Integration Context",
        "content": "This context should be used in the prompt"
    })

    session = SessionSchema(id="test-session", user_id="test-user", title="Test Session", updated_at=datetime.now())

    callback_mock = AsyncMock()

    session, messages = await session_manager.chat_ask_websocket(
        callback=callback_mock,
        user_id="test-user",
        session_id="test-session",
        message="Test message",
        agent_name="test-agent"
    )
    assert session is not None
    assert messages is not None
    assert any(msg.sender == "user" and msg.content == "Test message" for msg in messages)
    assert any(msg.sender == "assistant" and msg.content == "Final reply with context" for msg in messages)
    assert any(msg.sender == "system" and msg.content == "Intermediate system thought" for msg in messages)
    ranks = [msg.rank for msg in messages]
    assert sorted(ranks) == ranks  # Messages should be ordered by increasing rank
    assert callback_mock.call_count == 1


@pytest.mark.asyncio
async def test_session_manager_without_context(session_manager):
    session = SessionSchema(id="test-session-no-ctx", user_id="test-user", title="Test", updated_at=datetime.now())

    callback_mock = AsyncMock()

    result = await session_manager.chat_ask_websocket(
        callback=callback_mock,
        user_id="test-user",
        session_id="test-session-no-ctx",
        message="No context here",
        agent_name="nonexistent-agent"
    )

    assert callback_mock.call_count == 1


@pytest.mark.asyncio
async def test_refresh_context_integration(session_manager, context_service):
    context_service.save_context("test-agent", {
        "title": "Initial Context",
        "content": "This is the initial context"
    })

    _ = session_manager._get_agent_contexts("test-agent")  # cache fill

    context_service.save_context("test-agent", {
        "title": "Updated Context",
        "content": "This is an updated context"
    })

    session = SessionSchema(id="test-session-refresh", user_id="test-user", title="Refresh", updated_at=datetime.now())

    callback_mock = AsyncMock()

    session, messages = await session_manager.chat_ask_websocket(
        callback=callback_mock,
        user_id="test-user",
        session_id="test-session-refresh",
        message="Test message",
        agent_name="test-agent",
    )

    assert callback_mock.call_count == 1

    refreshed = session_manager.refresh_context_for_agent("test-agent")
    assert refreshed

    contexts = context_service.get_contexts("test-agent")
    titles = [c["title"] for c in contexts]
    assert "Initial Context" in titles
    assert "Updated Context" in titles
