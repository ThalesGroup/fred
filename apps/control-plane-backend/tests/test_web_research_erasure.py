# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
from types import SimpleNamespace

import httpx
import pytest
from control_plane_backend.users.web_research_erasure import erase_web_research_activity
from fastapi import HTTPException


@pytest.mark.asyncio
@pytest.mark.parametrize("status,failed", [(200, False), (404, False), (503, True)])
async def test_user_erasure_fanout_authentication_and_failure(status, failed):
    config = SimpleNamespace(
        platform=SimpleNamespace(
            runtime_catalog_sources=[
                SimpleNamespace(enabled=True, base_url="https://runtime"),
                SimpleNamespace(enabled=False, base_url="https://disabled"),
            ]
        )
    )
    calls = []

    def respond(request):
        calls.append(request)
        assert request.headers["authorization"] == "Bearer admin"
        assert request.url.path == "/agents/web-research/activity/users/user"
        return httpx.Response(status)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        if failed:
            with pytest.raises(HTTPException) as error:
                await erase_web_research_activity(
                    config, client, "user", "Bearer admin"
                )
            assert error.value.status_code == 503
        else:
            await erase_web_research_activity(config, client, "user", "Bearer admin")
    assert len(calls) == 1
