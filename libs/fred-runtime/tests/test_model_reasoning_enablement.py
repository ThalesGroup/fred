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
@pytest.mark.parametrize("effort", ["high", None])
async def test_transport_preserves_admitted_reasoning(effort):
    data = resolved_binding().model_dump(mode="json")
    data["inference"]["selection"]["options"]["reasoning_effort"] = effort
    binding = WeaverRuntimeBinding.model_validate(data)
    authority = TurnAuthority(binding, None)
    sent = []

    def send(request):
        sent.append(request)
        return httpx.Response(200, json={})

    with httpx.Client(transport=httpx.MockTransport(send)) as shared:
        with RunScope.open() as scope:
            authority.start(scope)
            scope.turn_authority = authority
            client, _ = checked_clients(
                authority, binding.inference, {"fixture"}, None
            )(shared, httpx.AsyncClient())
            payload = {"model": "first", "max_tokens": 50}
            if effort is not None:
                payload["reasoning_effort"] = effort
            client.post(
                "https://a.invalid/v1/chat/completions",
                headers={"Authorization": "Bearer fixture"},
                json=payload,
            )
            payload["reasoning_effort"] = "low" if effort else "high"
            with pytest.raises(AuthorityLostError):
                client.post(
                    "https://a.invalid/v1/chat/completions",
                    headers={"Authorization": "Bearer fixture"},
                    json=payload,
                )
            assert len(sent) == 1
            authority.close()
