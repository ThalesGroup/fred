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
    live_object_census,
    malloc_trim,
)
from fred_core.diagnostics import gc_diagnostics as gcd

# ---------------------------------------------------------------------------
# current_rss_kb / malloc_trim — real platform (whatever CI/dev runs on)
# ---------------------------------------------------------------------------


def test_current_rss_kb_matches_its_documented_contract():
    # None ("unreadable", e.g. a sandboxed process) or a positive KiB value —
    # never a hard assumption that this environment can read RSS at all.
    rss = current_rss_kb()
    assert rss is None or rss > 0


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
    # Skip rather than assert-and-fail if this environment can't read RSS at
    # all (e.g. a restricted CI sandbox) — that's a pre-existing environment
    # limitation, not a regression this test is meant to catch.
    if current_rss_kb() is None:
        pytest.skip("RSS unreadable in this environment even without simulation")
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

    expected_key = gcd._type_key(_Node())
    a, b = _Node(), _Node()
    a.other, b.other = b, a
    del a, b

    old_debug = gc.get_debug()
    try:
        report = collect_and_report_types(log=False)
        assert report.held_for_inspection >= 1
        assert any(name == expected_key for name, _count in report.top_types)
        # Regression check: the function must drop its own reference to the
        # collected garbage before its final gc.collect(), or that collect()
        # can't actually free anything and freed_after_clear is always 0.
        assert report.freed_after_clear >= 1
    finally:
        # The function itself clears gc.garbage internally; this just proves
        # the contract (no debug flags, no garbage) actually held afterward.
        assert gc.get_debug() == old_debug
        assert gc.garbage == []


# ---------------------------------------------------------------------------
# live_object_census
# ---------------------------------------------------------------------------


def test_live_object_census_returns_a_populated_result(caplog):
    with caplog.at_level(logging.WARNING):
        result = live_object_census(log=True)
    assert result.total_objects > 0
    assert result.total_bytes_shallow > 0
    # Not hard-asserted at 0: some real-world type in the test process's own
    # dependency graph could legitimately raise from __sizeof__. The
    # non-zero case has its own dedicated, forced test below.
    assert 0 <= result.sizing_failures <= result.total_objects
    assert result.rss_kb is None or result.rss_kb > 0
    assert result.top_by_count
    assert result.top_by_size
    assert any("[GC][census]" in r.message for r in caplog.records)


def test_live_object_census_can_skip_logging():
    result = live_object_census(log=False)
    assert result.total_objects > 0


def test_live_object_census_counts_reflect_a_known_live_object():
    class _Marker:
        pass

    markers = [_Marker() for _ in range(50)]
    try:
        result = live_object_census(top_n=1000, log=False)
        counts = dict(result.top_by_count)
        # Derived via _type_key(), not hardcoded as "_Marker": the key is
        # module-qualified (see _type_key's own tests), so a plain bare-name
        # assertion here would silently stop matching if that ever changes.
        expected_key = gcd._type_key(markers[0])
        assert counts.get(expected_key, 0) >= 50
    finally:
        del markers


def test_live_object_census_counts_sizing_failures_instead_of_swallowing_them(caplog):
    # A handful of real-world types raise from __sizeof__ (or lack one) —
    # simulate that instead of hoping to find one in the wild.
    class _BrokenSizeof:
        def __sizeof__(self):
            raise RuntimeError("no sizeof for you")

    broken = [_BrokenSizeof() for _ in range(10)]
    try:
        with caplog.at_level(logging.WARNING):
            result = live_object_census(log=True)
        assert result.sizing_failures >= 10
        assert any(
            "sizing_failures=" in r.message and "sizing_failures=0" not in r.message
            for r in caplog.records
        )
    finally:
        del broken


def test_type_key_keeps_builtins_bare():
    assert gcd._type_key({}) == "dict"
    assert gcd._type_key(()) == "tuple"


def test_type_key_disambiguates_same_named_classes_from_different_modules():
    # The exact regression this exists for: two classes named identically,
    # "defined in different modules" (simulated via __module__), must not
    # collapse into one census key.
    class Config:
        pass

    class _ConfigB:
        pass

    Config.__qualname__ = "Config"
    _ConfigB.__name__ = "Config"
    _ConfigB.__qualname__ = "Config"

    Config.__module__ = "fake_module_a"
    _ConfigB.__module__ = "fake_module_b"

    key_a = gcd._type_key(Config())
    key_b = gcd._type_key(_ConfigB())
    assert key_a != key_b
    assert key_a == "fake_module_a.Config"
    assert key_b == "fake_module_b.Config"


def test_type_key_qualifies_non_builtin_stdlib_types():
    # Copilot review on #2199: the docstring previously said "builtins/stdlib
    # types" stay bare, but the actual condition is __module__ == "builtins"
    # only — a non-builtin stdlib type like collections.Counter must still be
    # qualified, or a Counter and some hypothetical unrelated app-level
    # "Counter" class would collide in a report exactly like the bug this
    # module exists to prevent.
    from collections import Counter as StdlibCounter

    assert gcd._type_key(StdlibCounter()) == "collections.Counter"


def test_type_key_for_class_survives_a_hostile_metaclass():
    # chatgpt-codex-connector review on #2199: a class whose metaclass
    # overrides __getattribute__ and raises on __module__/__qualname__
    # access must not abort the whole census/report for every other
    # ordinary object — it degrades to a placeholder instead.
    class HostileMeta(type):
        def __getattribute__(cls, name):
            if name in ("__module__", "__qualname__", "__name__"):
                # Deliberately non-standard (a real __getattribute__ should
                # only ever raise AttributeError): getattr()'s own built-in
                # fallback already covers a conforming implementation, so a
                # plain AttributeError here wouldn't exercise the new
                # try/except Exception in _type_key_for_class at all. This
                # class exists specifically to prove that guard survives
                # non-conforming real-world code too.
                raise RuntimeError("nope")
            return type.__getattribute__(cls, name)

    class Hostile(metaclass=HostileMeta):
        pass

    key = gcd._type_key_for_class(Hostile)
    assert key.startswith("<unknown-type id=")


def test_live_object_census_caches_type_key_per_class(monkeypatch):
    # chatgpt-codex-connector review on #2199: with ~1.3M tracked objects
    # sharing a handful of types, _type_key_for_class() must be called at
    # most once per distinct class, not once per instance.
    calls: list[type] = []
    real = gcd._type_key_for_class

    def counting(cls):
        calls.append(cls)
        return real(cls)

    monkeypatch.setattr(gcd, "_type_key_for_class", counting)
    instances = [object() for _ in range(50)]
    try:
        result = gcd.live_object_census(log=False)
        assert result.total_objects >= 50
        assert calls.count(object) <= 1
    finally:
        del instances


def test_shallow_fraction_of_rss_handles_unknown_rss():
    assert gcd._shallow_fraction_of_rss(1000, None) == "RSS unknown"
    assert gcd._shallow_fraction_of_rss(1000, 0) == "RSS unknown"


def test_shallow_fraction_of_rss_computes_a_percentage():
    # 1024 bytes shallow out of 1 KiB (1024 bytes) RSS -> 100%.
    assert gcd._shallow_fraction_of_rss(1024, 1) == "100.0% of RSS"


def test_sigusr2_handler_runs_both_diagnostics(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        gcd,
        "collect_and_report_types",
        lambda: calls.append("types"),
    )
    monkeypatch.setattr(
        gcd,
        "live_object_census",
        lambda: calls.append("census"),
    )
    gcd._handle_sigusr2()
    assert calls == ["types", "census"]


# ---------------------------------------------------------------------------
# install_gc_diagnostics — signal registration
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not (hasattr(signal, "SIGUSR1") and hasattr(signal, "SIGUSR2")),
    reason="SIGUSR1/SIGUSR2 don't exist on this platform (e.g. Windows) — "
    "install_gc_diagnostics() is designed to degrade gracefully there, see "
    "test_install_skips_signals_gracefully_when_unavailable instead",
)
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
