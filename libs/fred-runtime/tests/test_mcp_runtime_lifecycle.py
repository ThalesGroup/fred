"""MCP runtime cleanup survives cancellation."""

import asyncio

import pytest
from fred_runtime.common.mcp_runtime import MCPRuntime


@pytest.mark.asyncio
async def test_close_retains_lifecycle_until_teardown_finishes() -> None:
    runtime = object.__new__(MCPRuntime)
    release = asyncio.Event()
    started = asyncio.Event()

    async def lifecycle() -> None:
        started.set()
        await release.wait()

    runtime._lifecycle_task = asyncio.create_task(lifecycle())
    runtime._stop_event = asyncio.Event()
    runtime._ready_event = asyncio.Event()
    runtime._lifecycle_error = None
    runtime._close_task = None
    close = asyncio.create_task(runtime.aclose())
    await started.wait()
    close.cancel()
    await asyncio.sleep(0)
    assert runtime._lifecycle_task is not None
    close.cancel()
    assert runtime._lifecycle_task is not None
    release.set()
    with pytest.raises(asyncio.CancelledError):
        _ = await close
    assert runtime._lifecycle_task is None
    assert runtime._close_task is not None and runtime._close_task.done()
    await runtime.aclose()


@pytest.mark.asyncio
async def test_cancelled_init_keeps_lifecycle_for_later_disposal() -> None:
    runtime = object.__new__(MCPRuntime)
    release = asyncio.Event()
    started = asyncio.Event()

    async def lifecycle() -> None:
        started.set()
        await release.wait()

    lifecycle_task = asyncio.create_task(lifecycle())
    runtime._lifecycle_task = lifecycle_task
    runtime._stop_event = asyncio.Event()
    runtime._ready_event = asyncio.Event()
    runtime._lifecycle_error = None
    runtime._close_task = None
    waiter = asyncio.create_task(runtime._await_lifecycle_attempt_completion())
    await started.wait()
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        _ = await waiter
    assert runtime._lifecycle_task is lifecycle_task
    release.set()
    await runtime.aclose()
    assert lifecycle_task.done()
    assert runtime._lifecycle_task is None
