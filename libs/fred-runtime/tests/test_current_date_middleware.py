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

"""Date context in the final ReAct and Deep model request."""

import httpx
import pytest
from fred_runtime.react.middleware.current_date import CurrentDateMiddleware
from fred_runtime.react.middleware.rate_limit_retry import RateLimitRetryMiddleware
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "saved_prompt",
    ["Agent instructions.", "Today is {today}.", "Today is 2022-01-01."],
)
async def test_existing_prompts_receive_fresh_date_each_model_call(
    monkeypatch: pytest.MonkeyPatch, saved_prompt: str
) -> None:
    dates = iter(("2026-11-25", "2026-11-26"))
    monkeypatch.setattr(
        "fred_runtime.react.middleware.current_date.current_date_instruction",
        lambda: f"The current UTC date is {next(dates)}.",
    )
    authored = (
        "<platform_instructions>\nPlatform rules.\n</platform_instructions>\n\n"
        "<platform_prompt>\nAdmin rules.\n</platform_prompt>\n\n"
        f"<agent_instructions>\n{saved_prompt}\n</agent_instructions>"
    )
    request = ModelRequest(
        model=FakeListChatModel(responses=["done"]),
        messages=[HumanMessage(content="What is today's date?")],
        system_message=SystemMessage(content=authored),
    )
    seen: list[str] = []

    async def handler(effective: ModelRequest) -> ModelResponse:
        seen.append(effective.system_prompt or "")
        return ModelResponse(result=[AIMessage(content="done")])

    middleware = CurrentDateMiddleware()
    await middleware.awrap_model_call(request, handler)
    await middleware.awrap_model_call(request, handler)

    assert request.system_prompt == authored
    assert len(seen) == 2
    for prompt, date in zip(seen, ("2026-11-25", "2026-11-26"), strict=True):
        assert prompt.startswith("<platform_instructions>\nPlatform rules.")
        assert "<platform_prompt>\nAdmin rules.\n</platform_prompt>" in prompt
        assert saved_prompt in prompt
        assert prompt.endswith(f"\n\nThe current UTC date is {date}.")


@pytest.mark.asyncio
async def test_prompt_without_platform_block_gets_date() -> None:
    request = ModelRequest(
        model=FakeListChatModel(responses=["done"]), messages=[], system_message=None
    )

    async def handler(effective: ModelRequest) -> ModelResponse:
        assert (effective.system_prompt or "").startswith("The current UTC date is ")
        return ModelResponse(result=[AIMessage(content="done")])

    await CurrentDateMiddleware().awrap_model_call(request, handler)


@pytest.mark.asyncio
async def test_rate_limit_retry_refreshes_date_between_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dates = iter(("2026-11-25", "2026-11-26"))
    monkeypatch.setattr(
        "fred_runtime.react.middleware.current_date.current_date_instruction",
        lambda: f"The current UTC date is {next(dates)}.",
    )
    binding = BoundRuntimeContext(
        runtime_context=RuntimeContext(),
        portable_context=PortableContext(
            request_id="r",
            correlation_id="c",
            actor="u",
            tenant="t",
            environment=PortableEnvironment.DEV,
        ),
    )
    retry = RateLimitRetryMiddleware(kpi=None, binding=binding)
    monkeypatch.setattr(retry, "_delay_for", lambda *_args: 0)
    request = ModelRequest(
        model=FakeListChatModel(responses=["done"]),
        messages=[],
        system_message=SystemMessage(content="Existing prompt"),
    )
    seen: list[str] = []

    async def model_call(effective: ModelRequest) -> ModelResponse:
        seen.append(effective.system_prompt or "")
        if len(seen) == 1:
            req = httpx.Request("POST", "https://model.invalid/v1/chat/completions")
            raise httpx.HTTPStatusError(
                "rate limited", request=req, response=httpx.Response(429, request=req)
            )
        return ModelResponse(result=[AIMessage(content="done")])

    await retry.awrap_model_call(
        request,
        lambda attempt: CurrentDateMiddleware().awrap_model_call(attempt, model_call),
    )
    assert "The current UTC date is 2026-11-25." in seen[0]
    assert "The current UTC date is 2026-11-26." in seen[1]
