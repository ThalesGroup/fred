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


@pytest.mark.parametrize("portable", [False, True])
@pytest.mark.parametrize(
    "changed", [None, "user_id", "session_id", "space_id", "agent_instance_id"]
)
def test_context_provenance_is_checked_for_runtime_and_portable_calls(
    portable, changed
):
    from fred_sdk.contracts.context import (
        PortableContext,
        PortableEnvironment,
        RuntimeContext,
    )

    binding = resolved_binding()
    fields = dict(
        user_id=binding.subject_id,
        session_id=binding.conversation_id,
        space_id=str(binding.space.id),
        agent_instance_id=str(binding.agent.instance_id),
    )
    if changed is not None:
        fields[changed] = "forged"
    if portable:
        space = fields.pop("space_id")
        instance = fields.pop("agent_instance_id")
        context = PortableContext(
            request_id="r",
            correlation_id="c",
            actor="person",
            tenant="default",
            environment=PortableEnvironment.DEV,
            **fields,
            baggage={"space_id": str(space), "agent_instance_id": str(instance)},
        )
    else:
        context = RuntimeContext.model_validate(fields)

    # RunScope teardown requires an active event loop.
    async def check():
        with RunScope.open() as scope:
            authority = TurnAuthority(binding, None)
            authority.start(scope)
            scope.turn_authority = authority
            if changed is None:
                authority.check_context(context, "template")
            else:
                with pytest.raises(AuthorityLostError):
                    authority.check_context(context, "template")

    asyncio.run(check())
