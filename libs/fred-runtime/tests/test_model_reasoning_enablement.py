# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Discovered aptitude, organization ceiling and question choice stay distinct."""

import httpx
import pytest
from fred_runtime.model_routing.guard import checked_clients
from fred_runtime.model_routing.turn import TurnAuthority
from fred_runtime.runtime_support.authority import AuthorityLostError
from fred_runtime.runtime_support.run_scope import RunScope
from fred_sdk.contracts.weaver import ModelOptions, WeaverRuntimeBinding
from pydantic import ValidationError
from weaver_fixtures import resolved_binding


def test_weaver_instance_options_refuse_reasoning_settings() -> None:

    with pytest.raises(ValidationError):
        ModelOptions.model_validate({"reasoning_effort": "high"})


@pytest.mark.asyncio
@pytest.mark.parametrize("capable", [True, False, None])
@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("requested", [True, False])
async def test_reasoning_transport_requires_all_three_facts(
    capable, enabled, requested
):
    data = resolved_binding().model_dump(mode="json")
    key = data["models"]["offers"][0]["key"]
    data["models"]["policy"]["reasoning_enabled"] = [key] if enabled else []
    data["models"]["offers"][0]["metadata"]["reasoning"] = capable
    binding = WeaverRuntimeBinding.model_validate(data)
    authority = TurnAuthority(binding, None, reasoning=requested)
    expected = "high" if capable is True and enabled and requested else None
    sent = []

    def send(request):
        sent.append(request)
        return httpx.Response(200, json={})

    with httpx.Client(transport=httpx.MockTransport(send)) as shared:
        with RunScope.open() as scope:
            authority.start(scope)
            scope.turn_authority = authority
            offer = binding.models.offers[0]
            assert authority.reasoning_effort(offer) == expected
            # Another permitted model cannot inherit the selected model's ceiling.
            assert authority.reasoning_effort(binding.models.offers[1]) is None
            client, _ = checked_clients(authority, offer, "fixture")(
                shared, httpx.AsyncClient()
            )
            payload = {"model": "first", "max_tokens": 50}
            if expected is not None:
                payload["reasoning_effort"] = expected
            client.post(
                "https://a.invalid/v1/chat/completions",
                headers={"Authorization": "Bearer fixture"},
                json=payload,
            )
            payload["reasoning_effort"] = "low" if expected else "high"
            with pytest.raises(AuthorityLostError):
                client.post(
                    "https://a.invalid/v1/chat/completions",
                    headers={"Authorization": "Bearer fixture"},
                    json=payload,
                )
            assert len(sent) == 1
            authority.close()
