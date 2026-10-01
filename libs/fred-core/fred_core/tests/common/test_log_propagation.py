# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software distributed
# under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for details.

import base64

import pytest
from fred_core.logs.context import log_context
from fred_core.logs.propagation import (
    decode_log_context,
    encode_log_context,
    outbound_context_headers,
)


def test_transport_accepts_bounded_json_and_rejects_unsafe_or_ambiguous_envelopes():
    values = {"custom": [True, None, {"step": 2}], "correlation_id": "journey"}
    encoded = encode_log_context(values)
    assert encoded is not None
    assert decode_log_context(encoded) == (values, None)
    assert encode_log_context({"custom": object()}) is None
    assert encode_log_context({"custom": "x" * 1025}) is None
    assert encode_log_context({str(i): i for i in range(33)}) is None
    assert encode_log_context({"custom": [[[[1]]]]}) is None
    assert encode_log_context({"custom": ["x" * 1024] * 4}) is None
    assert encode_log_context({"authorization": "credential-canary"}) is None
    assert encode_log_context({"custom": float("nan")}) is None
    assert encode_log_context({"custom": 2**63}) is None
    for payload in (
        b'{"v":2,"context":{}}',
        b'{"v":true,"context":{}}',
        b'{"v":1,"context":{"id":1,"id":2}}',
        b'{"v":1,"context":{"custom":NaN}}',
        b'{"v":1,"context":{"token":"credential-canary"}}',
        b"x" * 4097,
    ):
        values, reason = decode_log_context(
            base64.urlsafe_b64encode(payload).decode().rstrip("=")
        )
        assert values is None and reason is not None
    assert decode_log_context("a" * 8193) == (None, "oversized")
    with log_context(custom="bound"):
        headers = outbound_context_headers()
    # Only the bound bag is exported. An event-only extra is never part of it.
    assert decode_log_context(next(iter(headers.values()))) == (
        {"custom": "bound"},
        None,
    )


@pytest.mark.asyncio
async def test_mcp_inner_request_uses_admitted_context_and_a_fresh_request_id(
    monkeypatch,
):
    import json

    import httpx
    from fastapi import FastAPI, Request

    pytest.importorskip("fastapi_mcp")
    from fred_core.logs.context import current_context
    from fred_core.logs.http import RequestLoggingMiddleware
    from fred_core.logs.propagation import CONTEXT_HEADER
    from fred_core.security import mcp_delegation, oidc
    from fred_core.security.delegation import AssertedUser
    from fred_core.security.mcp_delegation_fastapi import DelegatedFastApiMCP

    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)
    received = []

    @app.get("/inside", operation_id="inside")
    async def inside(request: Request):
        received.append(request)
        return {
            "headers": dict(request.headers),
            "query": dict(request.query_params),
            "context": current_context(),
        }

    async def principal(request, caller, **kwargs):
        return AssertedUser(
            uid="person-a", run_id="run-a", agent_id="agent-a", client_id="caller-a"
        )

    monkeypatch.setattr(oidc, "resolve_request_principal", principal)
    monkeypatch.setattr(oidc, "decode_jwt", lambda token: None)
    auth = mcp_delegation.mcp_mount_auth(
        request=Request({"type": "http", "headers": []}),
        token="synthetic-bearer",  # nosec B106 - synthetic fixture, never a credential
    )
    await anext(auth)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app),
            base_url="http://local.invalid",
            follow_redirects=True,
        ) as client:
            # Exercise the changed bridge through real ASGI requests, without
            # booting an unrelated MCP server/session lifecycle.
            server = object.__new__(DelegatedFastApiMCP)
            server._forward_headers = set()
            with log_context(
                request_id="outer-request",
                correlation_id="journey",
                team_id="inherited-team",
            ):
                result = await server._execute_api_tool(
                    client,
                    "inside",
                    {"person": "model-person"},
                    {
                        "inside": {
                            "path": "/inside",
                            "method": "get",
                            "parameters": [
                                {"name": name, "in": "query"}
                                for name in ("person", "run", "agent")
                            ],
                        }
                    },
                )
    finally:
        await anext(auth, None)
    assert isinstance(result, list)
    assert getattr(result[0], "type") == "text"
    payload = json.loads(getattr(result[0], "text"))
    assert payload["query"] == {
        "person": "person-a",
        "run": "run-a",
        "agent": "agent-a",
    }
    assert decode_log_context(payload["headers"][CONTEXT_HEADER.lower()])[0] == {
        "correlation_id": "journey",
        "team_id": "inherited-team",
    }
    assert len(received) == 1
    assert payload["context"]["request_id"] != "outer-request"
