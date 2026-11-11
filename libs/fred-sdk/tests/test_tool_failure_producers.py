# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""SDK producers report a tool or agent failure in the shared vocabulary."""

from __future__ import annotations

import httpx
import pytest
from fred_sdk.contracts.context import (
    AgentInvocationRequest,
    ToolFailure,
    ToolFailureCode,
)
from fred_sdk.runtime_support.remote_agent_invoker import (
    RemoteSseAgentInvoker,
    RemoteSseAgentInvokerConfig,
)
from test_authored_tool_runtime import REQUEST, bind


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_an_authored_error_carries_the_code_its_author_chose():
    refused = await bind(
        lambda ctx: ctx.error("Missing id.", code=ToolFailureCode.invalid_arguments)
    )(REQUEST)
    unknown = await bind(lambda ctx: ctx.error("Something broke."))(REQUEST)

    assert refused.failure == ToolFailure(code=ToolFailureCode.invalid_arguments)
    assert unknown.failure == ToolFailure(code=ToolFailureCode.unexpected)


@pytest.mark.anyio
async def test_an_unhandled_authored_exception_is_unexpected():
    def handler(ctx):
        raise ValueError("synthetic tool failure")

    result = await bind(handler)(REQUEST)
    assert result.failure == ToolFailure(code=ToolFailureCode.unexpected)


def _invoker(handler) -> RemoteSseAgentInvoker:
    return RemoteSseAgentInvoker(
        config=RemoteSseAgentInvokerConfig(endpoint_url="http://agents.test/stream"),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def _request() -> AgentInvocationRequest:
    return AgentInvocationRequest(
        agent_id="remote.agent", message="hello", context=REQUEST.context
    )


@pytest.mark.anyio
async def test_a_remote_agent_http_status_is_classified_once():
    result = await _invoker(lambda request: httpx.Response(503)).invoke(_request())
    assert result.failure == ToolFailure(code=ToolFailureCode.service_busy, status=503)


@pytest.mark.anyio
async def test_a_remote_agent_timeout_is_a_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    result = await _invoker(handler).invoke(_request())
    assert result.failure == ToolFailure(code=ToolFailureCode.timeout)
