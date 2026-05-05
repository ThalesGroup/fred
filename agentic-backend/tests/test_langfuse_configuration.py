# Copyright Thales 2026
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

from __future__ import annotations

from typing import Any, AsyncIterator

import pytest
from langchain_core.messages import HumanMessage

from agentic_backend.common.langfuse_config import get_langfuse_credentials
from agentic_backend.common.structures import AgentSettings
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import AgentTuning
from agentic_backend.core.chatbot.stream_transcoder import StreamTranscoder
from agentic_backend.integrations.v2_runtime import adapters as v2_adapters


class _TestAgentFlow(AgentFlow):
    tuning = AgentTuning(role="test", description="test")


class _FakeUser:
    uid = "user-1"


class _FakeRuntimeContext:
    access_token = None
    refresh_token = None


class _ConfigCapturingAgent:
    def __init__(self) -> None:
        self.streaming_memory = None
        self.configs: list[dict[str, Any]] = []

    async def astream_updates(
        self,
        state: Any,
        *,
        config: Any = None,
        stream_mode: Any = None,
        context: Any = None,
    ) -> AsyncIterator[Any]:
        _ = state
        _ = stream_mode
        _ = context
        self.configs.append(dict(config or {}))
        if False:
            yield None


def test_get_langfuse_credentials_requires_explicit_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    assert get_langfuse_credentials() is None


def test_get_langfuse_credentials_accepts_legacy_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://langfuse.example/")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    assert get_langfuse_credentials() == (
        "https://langfuse.example",
        "pk-test",
        "sk-test",
    )


def test_build_langfuse_tracer_stays_disabled_without_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setattr(v2_adapters, "_LANGFUSE_TRACER", False)

    assert v2_adapters.build_langfuse_tracer() is None


def test_agent_flow_uses_shared_langfuse_client_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = object()
    monkeypatch.setattr(
        "agentic_backend.core.agents.agent_flow.build_langfuse_client",
        lambda: sentinel,
    )

    agent = _TestAgentFlow(agent_settings=AgentSettings(id="agent-1", name="Agent 1"))

    assert agent.langfuse_client is sentinel


@pytest.mark.asyncio
async def test_stream_transcoder_only_adds_callback_when_langfuse_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler_instances: list[object] = []

    class _FakeHandler:
        def __init__(self) -> None:
            handler_instances.append(self)

    monkeypatch.setattr(
        "agentic_backend.core.chatbot.stream_transcoder.CallbackHandler",
        _FakeHandler,
    )

    transcoder = StreamTranscoder(stream_flush_interval_ms=0)
    agent = _ConfigCapturingAgent()

    monkeypatch.setattr(
        "agentic_backend.core.chatbot.stream_transcoder.get_langfuse_credentials",
        lambda: None,
    )
    await transcoder.stream_agent_response(
        agent=agent,
        input_messages=[HumanMessage("hi")],
        session_id="sess-1",
        exchange_id="exch-1",
        agent_id="agent-1",
        base_rank=0,
        start_seq=0,
        callback=lambda message: None,
        user_context=_FakeUser(),
        runtime_context=_FakeRuntimeContext(),
    )
    assert "callbacks" not in agent.configs[-1]

    monkeypatch.setattr(
        "agentic_backend.core.chatbot.stream_transcoder.get_langfuse_credentials",
        lambda: ("https://langfuse.example", "pk-test", "sk-test"),
    )
    await transcoder.stream_agent_response(
        agent=agent,
        input_messages=[HumanMessage("hi")],
        session_id="sess-2",
        exchange_id="exch-2",
        agent_id="agent-1",
        base_rank=0,
        start_seq=0,
        callback=lambda message: None,
        user_context=_FakeUser(),
        runtime_context=_FakeRuntimeContext(),
    )
    assert len(handler_instances) == 1
    assert agent.configs[-1]["callbacks"] == [handler_instances[0]]
