# Copyright Thales 2025
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

"""Every legal shape of a token-refresh hook must drive 401 recovery.

An earlier static guard (`inspect.iscoroutinefunction` + a `.func` fallback) was
wrong in BOTH directions: it rejected an object with `async def __call__` and a
lambda returning a coroutine — both legal `Callable[[], Awaitable[str]]`, whose
agents then had expired-token recovery permanently disabled — while admitting a
synchronous wrapper that merely exposed `.func`, which is the exact `await <str>`
TypeError the guard existed to prevent. Deciding from the RESULT is what removes
the guessing; these cases pin it.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import pytest
from fred_runtime.common.kf_base_client import KfBaseClient
from fred_runtime.common.structures import AgentSettingsLike, resolve_refresh_result
from fred_sdk.contracts.context import RuntimeContext
from fred_sdk.contracts.models import AgentTuning, MCPServerRef

pytestmark = pytest.mark.asyncio


async def _coroutine_fn() -> str:
    return "fresh-token"


class _AsyncCallable:
    async def __call__(self) -> str:
        return "fresh-token"


class _SyncWrapperExposingFunc:
    """Sync __call__ but a coroutine function on `.func` — the false positive."""

    def __init__(self) -> None:
        self.func = _coroutine_fn

    def __call__(self) -> str:
        return "fresh-token"


@pytest.mark.parametrize(
    "hook",
    [
        _coroutine_fn,
        _AsyncCallable(),
        lambda: _coroutine_fn(),  # closure returning a coroutine
    ],
    ids=["coroutine_function", "async_dunder_call", "lambda_returning_coroutine"],
)
async def test_every_async_shape_resolves_to_the_token(hook):
    assert await resolve_refresh_result(hook(), object()) == "fresh-token"


async def test_sync_hook_is_used_and_loudly_reported(caplog):
    """A sync hook has already blocked the loop; its token is still valid.

    Refusing it turned one slow call into a permanently broken recovery path,
    so the token is used and the fault is named at ERROR.
    """
    hook = _SyncWrapperExposingFunc()

    with caplog.at_level(logging.ERROR):
        result = await resolve_refresh_result(hook(), hook)

    assert result == "fresh-token"
    assert "SYNCHRONOUS" in caplog.text
    assert "_SyncWrapperExposingFunc" in caplog.text


class _FakeAgentSettings:
    """Matches `AgentSettingsLike` (id / team_id / tuning / active_mcp_servers)."""

    id: str = "agent-1"
    team_id: str | None = "team-1"
    tuning: AgentTuning | None = None
    active_mcp_servers: Sequence[MCPServerRef] = ()


class _AgentWithEmptyRefresh:
    """Conforms to `KnowledgeFlowAgentContext`, but its hook resolves to an
    empty token — the shape `Protocol` alone cannot rule out, since
    `KnowledgeFlowAgentContext` isn't `@runtime_checkable`.
    """

    def __init__(self) -> None:
        self.runtime_context = RuntimeContext()
        self.agent_settings: AgentSettingsLike = _FakeAgentSettings()

    async def refresh_user_access_token(self) -> str:
        return ""


async def test_agent_hook_empty_token_fails_fast_instead_of_reporting_success(caplog):
    """`_try_refresh_token`'s agent-hook branch must not discard emptiness.

    `resolve_refresh_result` can degrade a hook's result to `""` without
    raising — its own docstring: "An empty token is what every caller already
    treats as 'refresh produced nothing'". The sibling `_refresh_cb` branch
    already checks `if not new_token` for this exact call shape; the
    agent-hook branch must do the same instead of unconditionally logging
    "succeeded" and returning True on an empty token.
    """
    client = KfBaseClient.__new__(KfBaseClient)
    client._agent = _AgentWithEmptyRefresh()
    client._refresh_cb = None

    with caplog.at_level(logging.ERROR):
        result = await client._try_refresh_token()

    assert result is False
    assert "Agent-led token refresh returned an empty token." in caplog.text
