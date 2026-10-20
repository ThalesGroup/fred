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

import asyncio
from datetime import UTC, datetime

from fred_runtime.react.middleware.tracing_kpi import TracingKpiMiddleware
from fred_runtime.runtime_support import current_date
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage


def test_current_date_instruction_refreshes_each_call(monkeypatch) -> None:
    class Clock:
        calls = 0

        @classmethod
        def now(cls, *, tz):
            assert tz is UTC
            cls.calls += 1
            return datetime(2026, 10, 20 if cls.calls == 1 else 21, tzinfo=UTC)

    monkeypatch.setattr(current_date, "datetime", Clock)

    assert "2026-10-20" in current_date.current_date_instruction()
    assert "2026-10-21" in current_date.current_date_instruction()


def test_current_date_block_exists_without_platform_file() -> None:
    prompt = current_date.add_current_date_to_system_prompt("<tools>\nSearch\n</tools>")
    assert prompt.startswith("<platform_instructions>\nCurrent UTC date: ")
    assert prompt.index("</platform_instructions>") < prompt.index("<tools>")


def test_model_boundary_refreshes_date_and_saved_prompts(monkeypatch) -> None:
    class Clock:
        calls = 0

        @classmethod
        def now(cls, *, tz):
            assert tz is UTC
            cls.calls += 1
            return datetime(2026, 10, 20 if cls.calls == 1 else 21, tzinfo=UTC)

    monkeypatch.setattr(current_date, "datetime", Clock)
    binding = BoundRuntimeContext(
        runtime_context=RuntimeContext(session_id="s", user_id="u", team_id="t"),
        portable_context=PortableContext(
            request_id="r",
            correlation_id="c",
            actor="u",
            tenant="t",
            environment=PortableEnvironment.DEV,
        ),
    )
    middleware = TracingKpiMiddleware(tracer=None, kpi=None, binding=binding)
    static_prompt = (
        "<platform_instructions>\nHOUSE RULES\n</platform_instructions>\n\n"
        "<platform_prompt>\nSAVED ADMIN PROMPT {today}\n</platform_prompt>\n\n"
        "<agent_instructions>\nSAVED AGENT PROMPT: "
        f"{current_date.DEFERRED_TODAY_TOKEN}\n</agent_instructions>"
    )
    request = ModelRequest(
        model=FakeListChatModel(responses=["ok"]),
        messages=[],
        system_prompt=static_prompt,
    )
    seen: list[str] = []

    async def handler(effective: ModelRequest) -> ModelResponse:
        seen.append(effective.system_prompt or "")
        return ModelResponse(result=[AIMessage(content="ok")])

    async def invoke_twice() -> None:
        await middleware.awrap_model_call(request, handler)
        await middleware.awrap_model_call(request, handler)

    asyncio.run(invoke_twice())

    assert len(seen) == 2
    assert "HOUSE RULES" in seen[0] and "SAVED ADMIN PROMPT {today}" in seen[0]
    assert "SAVED AGENT PROMPT: 2026-10-20" in seen[0]
    assert "Current UTC date: 2026-10-20" in seen[0]
    assert "SAVED AGENT PROMPT: 2026-10-21" in seen[1]
    assert "Current UTC date: 2026-10-21" in seen[1]
    assert request.system_prompt == static_prompt
