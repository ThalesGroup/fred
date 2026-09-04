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

"""`RemoteSseAgentInvoker` maps the callee's `final` event onto the result.

A callee's turn emits no `agent.turn_completed` of its own, so whatever the
invoker drops here is spend nobody can count — the same reason the in-process
invoker carries `token_usage`.
"""

from __future__ import annotations

import asyncio
import json

import httpx
from fred_sdk.contracts.context import (
    AgentInvocationRequest,
    AgentInvocationResult,
    PortableContext,
    PortableEnvironment,
)
from fred_sdk.runtime_support.remote_agent_invoker import (
    RemoteSseAgentInvoker,
    RemoteSseAgentInvokerConfig,
)

AGENT_ID = "v2.sample.assistant"
ENDPOINT = "https://agents.example.com/v2/execute/stream"


def _request() -> AgentInvocationRequest:
    return AgentInvocationRequest(
        agent_id=AGENT_ID,
        message="do the thing",
        context=PortableContext(
            request_id="req-1",
            correlation_id="corr-1",
            actor="alice",
            tenant="default",
            environment=PortableEnvironment.DEV,
            session_id="session-1",
            user_id="alice",
        ),
    )


def _invoke(final_event: dict) -> AgentInvocationResult:
    """Drive one invocation whose stream carries `final_event`."""

    body = f"data: {json.dumps(final_event)}\n\n"

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    invoker = RemoteSseAgentInvoker(
        config=RemoteSseAgentInvokerConfig(endpoint_url=ENDPOINT), client=client
    )

    async def _run() -> AgentInvocationResult:
        try:
            return await invoker.invoke(_request())
        finally:
            await client.aclose()

    return asyncio.run(_run())


def test_token_usage_from_the_final_event_reaches_the_caller() -> None:
    result = _invoke(
        {
            "kind": "final",
            "sequence": 0,
            "content": "ok",
            "token_usage": {"input_tokens": 1200, "output_tokens": 300},
        }
    )

    assert result.is_error is False
    assert result.content == "ok"
    assert result.token_usage == {"input_tokens": 1200, "output_tokens": 300}


def test_token_usage_is_none_when_the_callee_reports_none() -> None:
    result = _invoke({"kind": "final", "sequence": 0, "content": "ok"})

    assert result.is_error is False
    assert result.token_usage is None
