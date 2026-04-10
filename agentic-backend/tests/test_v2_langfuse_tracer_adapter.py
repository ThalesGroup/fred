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

from __future__ import annotations

from agentic_backend.core.agents.v2.contracts.context import (
    PortableContext,
    PortableEnvironment,
)
from agentic_backend.integrations.v2_runtime.adapters import LangfuseTracerAdapter


class _FakeSpan:
    def __init__(self) -> None:
        self.updated_metadata: dict[str, object] | None = None
        self.ended = False

    def update(self, *, metadata: dict[str, object] | None = None, **kwargs) -> object:
        _ = kwargs
        self.updated_metadata = metadata
        return object()

    def end(self, *, end_time: int | None = None) -> object:
        _ = end_time
        self.ended = True
        return object()


class _FakeLangfuseV4Client:
    def __init__(self) -> None:
        self.span = _FakeSpan()
        self.last_start_observation_args: dict[str, object] | None = None

    def create_trace_id(self, *, seed: str | None = None) -> str:
        return f"trace-{seed or 'none'}"

    def start_observation(self, **kwargs) -> _FakeSpan:
        self.last_start_observation_args = kwargs
        return self.span


def _portable_context() -> PortableContext:
    return PortableContext(
        request_id="req-1",
        correlation_id="corr-1",
        actor="chatbot",
        tenant="fred",
        environment=PortableEnvironment.DEV,
        session_id="sess-1",
        agent_id="agent-1",
        user_id="user-1",
        team_id="team-1",
    )


def test_langfuse_tracer_uses_start_observation_v4() -> None:
    client = _FakeLangfuseV4Client()
    tracer = LangfuseTracerAdapter(client)  # type: ignore[arg-type]

    span = tracer.start_span(
        name="v2.react.model",
        context=_portable_context(),
        attributes={"operation": "model_call"},
    )
    span.set_attribute("status", "ok")
    span.end()

    assert client.last_start_observation_args is not None
    assert client.last_start_observation_args["name"] == "v2.react.model"
    assert client.last_start_observation_args["as_type"] == "span"
    assert client.last_start_observation_args["trace_context"] == {
        "trace_id": "trace-corr-1"
    }
    assert client.last_start_observation_args["metadata"]["operation"] == "model_call"
    assert client.span.updated_metadata == {"status": "ok"}
    assert client.span.ended is True
