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

import pytest
from fred_runtime.common.structures import resolve_refresh_result

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
