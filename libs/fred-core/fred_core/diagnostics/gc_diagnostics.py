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
"""
Cross-platform reference-cycle GC diagnostics for Fred pods.

Why this module exists:
- pydantic-core (and other C-extension libraries) can leave reference cycles
  behind that plain refcounting never frees, only a forced `gc.collect()`
  does. ISSUE-010 (fredlab, 2026-07-31) found exactly this: a lazily-validated
  `Iterable[str]` pydantic field leaked a `ValidatorIterator` cycle on every
  construction, platform-wide, via this very library's own KPI writer.
  Diagnosing and mitigating that class of bug used to be hand-rolled once, in
  knowledge-flow-worker only. This module makes it a one-line `install_gc_diagnostics()`
  any Fred pod — ours or a third party's, built on fred-runtime or not — can
  opt into.
- macOS has neither `/proc` nor glibc's `malloc_trim`. Each capability here
  degrades independently and truthfully (RSS still works, via `psutil`;
  `malloc_trim` reports "unsupported") instead of crashing or silently lying.

How to use it:
    from fred_core.diagnostics import install_gc_diagnostics

    handle = install_gc_diagnostics(periodic_interval_s=300)
    ...
    await handle.stop()  # during pod shutdown

Manual triggers (best-effort, Unix + main-thread only — see install_gc_diagnostics):
    kubectl exec <pod> -- kill -USR1 1   # collect_and_trim: one-line RSS delta
    kubectl exec <pod> -- kill -USR2 1   # collect_and_report_types: + object types
"""

from __future__ import annotations

import asyncio
import ctypes
import ctypes.util
import gc
import logging
import os
import platform
import signal
from collections import Counter
from contextlib import suppress
from dataclasses import dataclass

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_ENV_VAR = "FRED_GC_DIAGNOSTICS_INTERVAL_SEC"


def current_rss_kb() -> int | None:
    """Current resident set size, in KiB, right now — unlike
    resource.getrusage().ru_maxrss (a peak since process start that never
    decreases). Cross-platform (Linux/macOS/Windows) via `psutil`. Returns
    None, never raises, if it can't be read (e.g. a sandboxed process)."""
    try:
        import psutil

        return psutil.Process(os.getpid()).memory_info().rss // 1024
    except Exception:
        logger.debug("[fred-core][gc-diagnostics] RSS read failed", exc_info=True)
        return None


def malloc_trim() -> bool:
    """Return freed pymalloc arenas to the OS via glibc's malloc_trim(0).
    CPython's allocator doesn't do this on its own, so gc.collect() alone can
    look like a no-op from `kubectl top`/Activity Monitor even after
    genuinely freeing objects.

    Linux/glibc-only — macOS's libSystem and musl libc (Alpine) have no
    equivalent symbol. This is a safe no-op (returns False) everywhere else;
    it never raises."""
    if platform.system() != "Linux":
        return False
    try:
        libc_path = ctypes.util.find_library("c")
        if libc_path is None:
            return False
        libc = ctypes.CDLL(libc_path)
        if not hasattr(libc, "malloc_trim"):
            return False  # musl (Alpine): no malloc_trim symbol
        libc.malloc_trim(0)
        return True
    except OSError:
        return False


def _format_rss_delta(before_kb: int | None, after_kb: int | None) -> str:
    """Render an RSS before->after pair for logging, without producing a
    misleading delta when either sample is unreadable (current_rss_kb()'s
    None case — e.g. `None -> 1234Ki` should never read as a numeric drop)."""
    if before_kb is None or after_kb is None:
        return f"{before_kb}Ki -> {after_kb}Ki (delta unknown, RSS unreadable)"
    return f"{before_kb}Ki -> {after_kb}Ki (delta {before_kb - after_kb}Ki)"


@dataclass(frozen=True)
class GCTrimResult:
    label: str
    collected: int
    uncollectable: int
    trimmed: bool
    rss_before_kb: int | None
    rss_after_kb: int | None


def collect_and_trim(label: str = "manual", *, log: bool = True) -> GCTrimResult:
    """Force a full GC cycle + malloc_trim(0). RSS drop -> reference-cycle
    garbage (plain refcounting never frees it) or reclaimed arenas. RSS
    unchanged -> either a real reference is still held, or the memory is
    native (a C extension, e.g. onnxruntime/docling), outside gc's/
    malloc_trim's reach."""
    before_kb = current_rss_kb()
    collected = gc.collect()
    uncollectable = len(gc.garbage)
    trimmed = malloc_trim()
    after_kb = current_rss_kb()
    result = GCTrimResult(label, collected, uncollectable, trimmed, before_kb, after_kb)
    if log:
        logger.warning(
            "[GC][%s] collected=%d uncollectable=%d trimmed=%s RSS %s",
            label,
            collected,
            uncollectable,
            trimmed,
            _format_rss_delta(before_kb, after_kb),
        )
    return result


@dataclass(frozen=True)
class GCTypeReport:
    collected: int
    held_for_inspection: int
    freed_after_clear: int
    trimmed: bool
    rss_before_kb: int | None
    rss_after_kb: int | None
    top_types: tuple[tuple[str, int], ...]


def collect_and_report_types(top_n: int = 20, *, log: bool = True) -> GCTypeReport:
    """Heavier variant of collect_and_trim: reports WHICH object types make up
    the reference-cycle garbage, not just a count (this is how ISSUE-010 was
    found live). gc.DEBUG_SAVEALL keeps this one collection's cyclic garbage
    reachable via gc.garbage instead of destroying it immediately, so its
    types can be inspected — then gc.garbage is cleared and re-collected so
    nothing stays pinned."""
    before_kb = current_rss_kb()
    old_flags = gc.get_debug()
    gc.set_debug(gc.DEBUG_SAVEALL)
    collected = gc.collect()
    gc.set_debug(old_flags)

    top_types = tuple(Counter(type(o).__name__ for o in gc.garbage).most_common(top_n))
    garbage_count = len(gc.garbage)
    gc.garbage.clear()
    freed_after_clear = gc.collect()
    trimmed = malloc_trim()
    after_kb = current_rss_kb()
    result = GCTypeReport(
        collected=collected,
        held_for_inspection=garbage_count,
        freed_after_clear=freed_after_clear,
        trimmed=trimmed,
        rss_before_kb=before_kb,
        rss_after_kb=after_kb,
        top_types=top_types,
    )
    if log:
        logger.warning(
            "[GC][types] collected=%d held_for_inspection=%d freed_after_clear=%d trimmed=%s RSS %s top_types=%s",
            collected,
            garbage_count,
            freed_after_clear,
            trimmed,
            _format_rss_delta(before_kb, after_kb),
            top_types,
        )
    return result


async def _periodic_loop(interval_s: float) -> None:
    while True:
        await asyncio.sleep(interval_s)
        collect_and_trim("periodic")


def _periodic_interval_from_env(env_var: str) -> float:
    raw = os.environ.get(env_var, "0")
    try:
        return float(raw)
    except ValueError:
        logger.warning(
            "[fred-core][gc-diagnostics] Invalid %s=%r, ignoring (periodic GC disabled)",
            env_var,
            raw,
        )
        return 0.0


class GCDiagnosticsHandle:
    """Returned by install_gc_diagnostics(). Call `await handle.stop()` during
    pod shutdown to cancel the periodic task cleanly; safe to call even when
    no periodic task was started."""

    def __init__(
        self, *, signals_installed: bool, tasks: list[asyncio.Task[None]]
    ) -> None:
        self.signals_installed = signals_installed
        self._tasks = tasks

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()


def install_gc_diagnostics(
    *,
    loop: asyncio.AbstractEventLoop | None = None,
    periodic_interval_s: float | None = None,
    interval_env_var: str = DEFAULT_INTERVAL_ENV_VAR,
    manual_signals: bool = True,
) -> GCDiagnosticsHandle:
    """One-call installer for a Fred pod's GC diagnostics. Call once during
    pod startup (FastAPI lifespan / worker main()); call `await handle.stop()`
    during shutdown.

    - manual_signals=True (default): registers SIGUSR1 (-> collect_and_trim)
      and SIGUSR2 (-> collect_and_report_types), e.g.
      `kubectl exec <pod> -- kill -USR1 1`. Best-effort and never fatal: a
      platform without these signals (Windows) or a loop/thread that can't
      register asyncio signal handlers (also Windows, or not the main
      thread) just skips this with a warning — the pod still starts. macOS
      and Linux both support this normally.
    - periodic_interval_s: seconds between automatic collect_and_trim() runs.
      None (default) reads `interval_env_var` (FRED_GC_DIAGNOSTICS_INTERVAL_SEC
      unless overridden — e.g. pass interval_env_var="KF_WORKER_GC_INTERVAL_SEC"
      to preserve an existing app-specific opt-in). <= 0 disables it.
    """
    signals_installed = False
    if manual_signals:
        sigusr1 = getattr(signal, "SIGUSR1", None)
        sigusr2 = getattr(signal, "SIGUSR2", None)
        if sigusr1 is None or sigusr2 is None:
            logger.warning(
                "[fred-core][gc-diagnostics] SIGUSR1/SIGUSR2 not available on this "
                "platform (%s) — manual triggers disabled",
                platform.system(),
            )
        else:
            try:
                active_loop = loop or asyncio.get_running_loop()
                active_loop.add_signal_handler(
                    sigusr1, lambda: collect_and_trim("SIGUSR1")
                )
                active_loop.add_signal_handler(sigusr2, collect_and_report_types)
                signals_installed = True
            except (NotImplementedError, RuntimeError) as exc:
                logger.warning(
                    "[fred-core][gc-diagnostics] SIGUSR1/SIGUSR2 manual triggers "
                    "unavailable on this platform/thread: %s",
                    exc,
                )

    interval_s = (
        periodic_interval_s
        if periodic_interval_s is not None
        else _periodic_interval_from_env(interval_env_var)
    )
    tasks: list[asyncio.Task[None]] = []
    if interval_s > 0:
        logger.warning(
            "[fred-core][gc-diagnostics] periodic gc.collect()+malloc_trim() enabled every %.0fs",
            interval_s,
        )
        tasks.append(asyncio.create_task(_periodic_loop(interval_s)))

    return GCDiagnosticsHandle(signals_installed=signals_installed, tasks=tasks)
