# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Prepared local invocation/transport cases; no real provider is used."""

import asyncio
import json

import httpx
import pytest
from fred_runtime.model_routing.guard import checked_clients
from fred_runtime.model_routing.turn import TurnAuthority, current_turn
from fred_runtime.runtime_support.authority import AuthorityLostError
from fred_runtime.runtime_support.run_scope import RunScope
from weaver_fixtures import resolved_binding


@pytest.mark.asyncio
async def test_ten_calls_retries_and_child_share_one_context():
    binding = resolved_binding()
    authority = TurnAuthority(binding, None)
    calls = []

    async def send(request):
        calls.append(request)
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as shared:
        with RunScope.open() as scope:
            authority.start(scope)
            scope.turn_authority = authority
            _, client = checked_clients(authority, binding.models.offers[0], "fixture")(
                httpx.Client(), shared
            )
            for _ in range(10):
                await client.post(
                    "https://a.invalid/v1/chat/completions",
                    headers={"Authorization": "Bearer fixture"},
                    json={"model": "first", "max_tokens": 50},
                )

            async def child():
                assert current_turn() is authority
                authority.check(agent_id="template")
                with pytest.raises(AuthorityLostError):
                    authority.check(agent_id="another-template")

            await asyncio.create_task(child())
            authority.close()
            with pytest.raises(AuthorityLostError):
                await client.post(
                    "https://a.invalid/v1/chat/completions",
                    headers={"Authorization": "Bearer fixture"},
                    json={"model": "first", "max_tokens": 50},
                )
        assert len(calls) == 10
        with RunScope.open() as scope:
            with pytest.raises(AuthorityLostError):
                authority.start(scope)


@pytest.mark.asyncio
async def test_concurrent_sources_keep_credentials_and_destinations_isolated():
    requests = []

    async def send(request):
        requests.append(
            (
                str(request.url),
                request.headers["authorization"],
                json.loads(request.content)["model"],
            )
        )
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as shared:

        async def turn(source):
            binding = resolved_binding(source=source)
            authority = TurnAuthority(binding, None)
            with RunScope.open() as scope:
                authority.start(scope)
                scope.turn_authority = authority
                _, client = checked_clients(
                    authority, binding.models.offers[0], source
                )(httpx.Client(), shared)
                await client.post(
                    f"https://{source}.invalid/v1/chat/completions",
                    headers={"Authorization": f"Bearer {source}"},
                    json={"model": "first", "max_tokens": 50},
                )

        await asyncio.gather(turn("a"), turn("b"))
    assert set(requests) == {
        ("https://a.invalid/v1/chat/completions", "Bearer a", "first"),
        ("https://b.invalid/v1/chat/completions", "Bearer b", "first"),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"model": "other", "max_tokens": 50},
        {"model": "first", "max_tokens": 51},
        {"model": "first", "reasoning_effort": "high", "max_tokens": 50},
    ],
)
async def test_transformed_requests_cannot_widen_model_or_options(payload):
    binding = resolved_binding()
    authority = TurnAuthority(binding, None)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: pytest.fail("must not send"))
    ) as shared:
        with RunScope.open() as scope:
            authority.start(scope)
            scope.turn_authority = authority
            _, client = checked_clients(authority, binding.models.offers[0], "fixture")(
                httpx.Client(), shared
            )
            with pytest.raises(AuthorityLostError):
                await client.post(
                    "https://a.invalid/v1/chat/completions",
                    headers={"Authorization": "Bearer fixture"},
                    json=payload,
                )
