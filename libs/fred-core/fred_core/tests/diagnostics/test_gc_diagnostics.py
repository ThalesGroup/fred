# Copyright Thales 2026
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

import asyncio
import gc
import logging
import signal
from typing import cast

import pytest
from fred_core.diagnostics import (
    collect_and_report_types,
    collect_and_trim,
    current_rss_kb,
    install_gc_diagnostics,
    malloc_trim,
)
from fred_core.diagnostics import gc_diagnostics as gcd

# ---------------------------------------------------------------------------
# current_rss_kb / malloc_trim — real platform (whatever CI/dev runs on)
# ---------------------------------------------------------------------------


def test_current_rss_kb_returns_a_positive_int_on_this_platform():
    rss = current_rss_kb()
    assert rss is not None
    assert rss > 0


def test_current_rss_kb_returns_none_without_raising_when_psutil_fails(monkeypatch):
    # psutil is imported lazily inside current_rss_kb(); patching the real
    # module's Process class is what that inner `import psutil` will resolve.
    import psutil

    def _boom(_pid):
        raise RuntimeError("no /proc here")

    monkeypatch.setattr(psutil, "Process", _boom)
    assert current_rss_kb() is None


def test_malloc_trim_never_raises_regardless_of_platform():
    # Real platform smoke test: whatever it returns, it must not raise.
    assert malloc_trim() in (True, False)


# ---------------------------------------------------------------------------
# macOS / non-Linux simulation — the specific "no problem on macOS" contract
# ---------------------------------------------------------------------------


def test_malloc_trim_is_a_safe_noop_on_macos(monkeypatch):
    monkeypatch.setattr(gcd.platform, "system", lambda: "Darwin")
    assert malloc_trim() is False


def test_malloc_trim_is_a_safe_noop_when_libc_symbol_is_missing(monkeypatch):
    # Simulates musl (Alpine): libc exists but has no malloc_trim symbol.
    monkeypatch.setattr(gcd.platform, "system", lambda: "Linux")

    class _FakeLibc:
        def __getattr__(self, _name):
            raise AttributeError

    monkeypatch.setattr(gcd.ctypes.util, "find_library", lambda _name: "libc.so")
    monkeypatch.setattr(gcd.ctypes, "CDLL", lambda _path: _FakeLibc())
    assert malloc_trim() is False


def test_current_rss_kb_works_even_when_platform_is_simulated_as_macos(monkeypatch):
    # psutil itself is genuinely cross-platform — RSS reading must keep
    # working (not silently degrade) when malloc_trim's platform gate fires.
    monkeypatch.setattr(gcd.platform, "system", lambda: "Darwin")
    assert current_rss_kb() is not None


# ---------------------------------------------------------------------------
# collect_and_trim / collect_and_report_types
# ---------------------------------------------------------------------------


def test_collect_and_trim_returns_a_populated_result(caplog):
    with caplog.at_level(logging.WARNING):
        result = collect_and_trim("unit-test")
    assert result.label == "unit-test"
    assert result.collected >= 0
    assert result.uncollectable >= 0
    assert any("[GC][unit-test]" in r.message for r in caplog.records)


def test_collect_and_trim_can_skip_logging():
    result = collect_and_trim("silent", log=False)
    assert result.label == "silent"


def test_collect_and_report_types_leaves_nothing_pinned_in_gc_garbage():
    # Build genuine cyclic garbage so the report has something to find.
    class _Node:
        def __init__(self) -> None:
            self.other: "_Node | None" = None

    a, b = _Node(), _Node()
    a.other, b.other = b, a
    del a, b

    old_debug = gc.get_debug()
    try:
        report = collect_and_report_types(log=False)
        assert report.held_for_inspection >= 1
        assert any(name == "_Node" for name, _count in report.top_types)
    finally:
        # The function itself clears gc.garbage internally; this just proves
        # the contract (no debug flags, no garbage) actually held afterward.
        assert gc.get_debug() == old_debug
        assert gc.garbage == []


# ---------------------------------------------------------------------------
# install_gc_diagnostics — signal registration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_install_registers_signal_handlers_on_this_platform():
    handle = install_gc_diagnostics(periodic_interval_s=0)
    try:
        assert handle.signals_installed is True
    finally:
        await handle.stop()
        loop = asyncio.get_running_loop()
        loop.remove_signal_handler(signal.SIGUSR1)
        loop.remove_signal_handler(signal.SIGUSR2)


@pytest.mark.asyncio
async def test_install_skips_signals_gracefully_when_unavailable(monkeypatch, caplog):
    # Simulates Windows: signal.SIGUSR1/SIGUSR2 simply don't exist there.
    monkeypatch.delattr(signal, "SIGUSR1", raising=False)
    monkeypatch.delattr(signal, "SIGUSR2", raising=False)
    with caplog.at_level(logging.WARNING):
        handle = install_gc_diagnostics(periodic_interval_s=0)
    assert handle.signals_installed is False
    assert any("not available on this platform" in r.message for r in caplog.records)
    await handle.stop()  # must not raise even though nothing was installed


@pytest.mark.asyncio
async def test_install_handles_add_signal_handler_raising(monkeypatch, caplog):
    class _FakeLoop:
        def add_signal_handler(self, *_args, **_kwargs):
            raise NotImplementedError("no signals on this event loop")

    fake_loop = cast(asyncio.AbstractEventLoop, _FakeLoop())
    with caplog.at_level(logging.WARNING):
        handle = install_gc_diagnostics(loop=fake_loop, periodic_interval_s=0)
    assert handle.signals_installed is False
    assert any(
        "unavailable on this platform/thread" in r.message for r in caplog.records
    )
    await handle.stop()


# ---------------------------------------------------------------------------
# install_gc_diagnostics — periodic task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_install_with_no_interval_starts_no_periodic_task():
    handle = install_gc_diagnostics(periodic_interval_s=0, manual_signals=False)
    assert handle._tasks == []
    await handle.stop()


@pytest.mark.asyncio
async def test_install_periodic_task_runs_and_stops_cleanly(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(gcd, "collect_and_trim", lambda label: calls.append(label))

    handle = install_gc_diagnostics(periodic_interval_s=0.01, manual_signals=False)
    await asyncio.sleep(0.05)
    await handle.stop()

    assert calls, "periodic task never fired"
    assert all(c == "periodic" for c in calls)
    assert handle._tasks == []
    # Give the cancelled task's wrapping coroutine a beat to finish unwinding.
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_install_reads_interval_from_default_env_var(monkeypatch):
    monkeypatch.setenv(gcd.DEFAULT_INTERVAL_ENV_VAR, "0.01")
    handle = install_gc_diagnostics(manual_signals=False)
    try:
        assert len(handle._tasks) == 1
    finally:
        await handle.stop()


@pytest.mark.asyncio
async def test_install_reads_interval_from_custom_env_var_name():
    import os

    os.environ["MY_APP_GC_INTERVAL_SEC"] = "0.01"
    try:
        handle = install_gc_diagnostics(
            manual_signals=False, interval_env_var="MY_APP_GC_INTERVAL_SEC"
        )
        try:
            assert len(handle._tasks) == 1
        finally:
            await handle.stop()
    finally:
        del os.environ["MY_APP_GC_INTERVAL_SEC"]


@pytest.mark.asyncio
async def test_install_ignores_invalid_env_var_value(monkeypatch, caplog):
    monkeypatch.setenv(gcd.DEFAULT_INTERVAL_ENV_VAR, "not-a-number")
    with caplog.at_level(logging.WARNING):
        handle = install_gc_diagnostics(manual_signals=False)
    assert handle._tasks == []
    assert any("Invalid" in r.message for r in caplog.records)
    await handle.stop()


@pytest.mark.asyncio
async def test_handle_stop_is_idempotent_and_safe_without_periodic_task():
    handle = install_gc_diagnostics(periodic_interval_s=0, manual_signals=False)
    await handle.stop()
    await handle.stop()  # second call must not raise
