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

import asyncio
from typing import Any, cast

import pytest
from fred_runtime.app import agent_app as agent_app_module
from fred_runtime.app import session_title
from fred_runtime.model_routing import (
    ModelRoutingPolicy,
    ModelRoutingResolver,
    RoutedChatModelFactory,
)
from fred_runtime.runtime_context import (
    RuntimeConfig,
    RuntimeContext,
    set_runtime_context,
)
from langchain_core.messages import AIMessage, BaseMessage


class _Model:
    def __init__(self, reply: str | Exception) -> None:
        self.reply = reply
        self.calls: list[list[BaseMessage]] = []

    async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
        self.calls.append(messages)
        if isinstance(self.reply, Exception):
            raise self.reply
        return AIMessage(content=self.reply)


def _install(model: _Model) -> None:
    class _Factory(RoutedChatModelFactory):
        def build_chat_for_profile(self, profile_id: str | None, **_kw: Any) -> Any:
            return model, "chat.default", None

    factory = _Factory(
        resolver=ModelRoutingResolver(
            ModelRoutingPolicy(default_profile_by_capability={}, profiles=())
        )
    )
    set_runtime_context(
        RuntimeContext(
            RuntimeConfig(
                knowledge_flow_url="http://kf.invalid", chat_model_factory=factory
            )
        )
    )


@pytest.fixture(autouse=True)
def _reset_context():
    yield
    set_runtime_context(None)


def test_title_is_cleaned_and_bounded() -> None:
    model = _Model('"Revue des ventes du T3."\nextra line')
    _install(model)
    title = asyncio.run(session_title.propose_session_title("x" * 5000))
    assert title == "Revue des ventes du T3"
    sent = cast(str, model.calls[0][1].content)
    assert len(sent) == session_title.MAX_INPUT_CHARS


def test_model_failure_gives_no_title() -> None:
    _install(_Model(RuntimeError("provider down")))
    assert asyncio.run(session_title.propose_session_title("hello")) is None


def test_blank_input_makes_no_call() -> None:
    model = _Model("unused")
    _install(model)
    assert asyncio.run(session_title.propose_session_title("  ")) is None
    assert model.calls == []


def _kinds(
    monkeypatch: pytest.MonkeyPatch, context: dict[str, Any], title: str | None
) -> list[str]:
    async def _inner(*_args: Any, **_kwargs: Any):
        yield {"kind": "status", "status": "thinking"}
        await asyncio.sleep(0)  # the turn's own model call: the title gets ready
        yield {"kind": "assistant_delta", "delta": "hi"}
        yield {"kind": "final", "content": "hi"}

    async def _propose(user_input: str) -> str | None:
        return title

    monkeypatch.setattr(
        agent_app_module, "_iterate_runtime_event_payloads_inner", _inner
    )
    monkeypatch.setattr(agent_app_module, "propose_session_title", _propose)
    request = agent_app_module._AgentExecuteRequest.model_construct(
        message="hello", context=context, resume_payload=None
    )

    async def _collect() -> list[dict]:
        return [
            payload
            async for payload in agent_app_module._iterate_runtime_event_payloads(
                cast(Any, None), request
            )
        ]

    payloads = asyncio.run(_collect())
    assert all(p["title"] == title for p in payloads if p["kind"] == "session_title")
    return [p["kind"] for p in payloads]


def test_title_streams_once_as_soon_as_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _kinds(monkeypatch, {"auto_title": True}, "Greeting") == [
        "status",
        "session_title",
        "assistant_delta",
        "final",
    ]


def test_no_title_event_unless_asked_and_generated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plain = ["status", "assistant_delta", "final"]
    assert _kinds(monkeypatch, {}, "Greeting") == plain
    assert _kinds(monkeypatch, {"auto_title": True}, None) == plain
