# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Exercise supported authored tool forms at the real SDK invocation boundary."""

import asyncio
import threading
from contextvars import ContextVar
from functools import partial

import pytest
from fred_sdk.authoring.authored_tool_runtime import (
    _AuthorRuntime,
    _AuthorTool,
    _bind_tool_handler,
)
from fred_sdk.contracts.context import (
    PortableContext,
    PortableEnvironment,
    ToolInvocationRequest,
)
from pydantic import BaseModel


@pytest.fixture
def anyio_backend():
    return "asyncio"


class Empty(BaseModel):
    pass


def bind(handler):
    return _bind_tool_handler(
        _AuthorTool("test:block", "block", None, Empty, handler),
        object.__new__(_AuthorRuntime),
    )


REQUEST = ToolInvocationRequest(
    tool_ref="test:block",
    payload={},
    context=PortableContext(
        request_id="test",
        correlation_id="test",
        actor="test",
        tenant="test",
        environment=PortableEnvironment.DEV,
    ),
)


@pytest.mark.anyio
async def test_sync_tool_yields_loop_and_preserves_context():
    context = ContextVar("tool_test", default="missing")
    token = context.set("caller")
    release = threading.Event()
    entered = asyncio.Event()
    loop = asyncio.get_running_loop()
    caller_thread = threading.get_ident()

    def handler(ctx):
        assert threading.get_ident() != caller_thread
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(2)
        return context.get()

    task = asyncio.create_task(bind(handler)(REQUEST))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        release.set()  # Requires the event loop to run while the tool is blocked.
        result = await task
        assert not result.is_error
        assert result.blocks[0].text == "caller"
    finally:
        release.set()
        await task
        context.reset(token)


@pytest.mark.anyio
@pytest.mark.parametrize("form", ["async", "async_callable", "partial", "sync_factory"])
async def test_async_tool_forms_keep_owner_loop(form):
    loop = asyncio.get_running_loop()

    async def handler(ctx):
        assert asyncio.get_running_loop() is loop
        return "ok"

    class AsyncCallable:
        async def __call__(self, ctx):
            return await handler(ctx)

    callables = {
        "async": handler,
        "async_callable": AsyncCallable(),
        "partial": partial(handler),
        "sync_factory": lambda ctx: handler(ctx),
    }
    result = await bind(callables[form])(REQUEST)
    assert not result.is_error
    assert result.blocks[0].text == "ok"


@pytest.mark.anyio
@pytest.mark.parametrize("error", [ValueError, StopIteration])
async def test_sync_tool_errors_complete_without_hanging(error):
    def handler(ctx):
        raise error("synthetic tool failure")

    result = await asyncio.wait_for(bind(handler)(REQUEST), 1)
    assert result.is_error


@pytest.mark.anyio
async def test_cancel_sync_tool_does_not_replay_or_wait_for_worker():
    release, finished = threading.Event(), threading.Event()
    entered = asyncio.Event()
    loop = asyncio.get_running_loop()
    calls = []

    def handler(ctx):
        calls.append(1)
        loop.call_soon_threadsafe(entered.set)
        try:
            assert release.wait(2)
            return "ok"
        finally:
            finished.set()

    task = asyncio.create_task(bind(handler)(REQUEST))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert calls == [1]
        assert not finished.is_set()  # Running synchronous code cannot be killed.
    finally:
        release.set()
        assert await asyncio.to_thread(finished.wait, 2)
