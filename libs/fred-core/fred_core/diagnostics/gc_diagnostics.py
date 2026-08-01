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
    kubectl exec <pod> -- kill -USR2 1   # collect_and_report_types + live_object_census:
                                          # uncollected-cycle types, then a full census
                                          # of every reachable object (not just garbage)
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
import sys
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
    except Exception:
        logger.debug("[fred-core][gc-diagnostics] malloc_trim failed", exc_info=True)
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
    types can be inspected — then only the entries THIS call added are
    cleared and re-collected, leaving any pre-existing gc.garbage contents
    (and the previous debug flags) untouched even if collection raises."""
    before_kb = current_rss_kb()
    old_flags = gc.get_debug()
    pre_existing_garbage_count = len(gc.garbage)
    try:
        gc.set_debug(gc.DEBUG_SAVEALL)
        collected = gc.collect()
    finally:
        gc.set_debug(old_flags)

    new_garbage = gc.garbage[pre_existing_garbage_count:]
    top_types = tuple(Counter(type(o).__name__ for o in new_garbage).most_common(top_n))
    garbage_count = len(new_garbage)
    del gc.garbage[pre_existing_garbage_count:]
    # Drop our own reference too, or the collect() below can't free these.
    del new_garbage
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


@dataclass(frozen=True)
class LiveObjectCensus:
    total_objects: int
    total_bytes_shallow: int
    top_by_count: tuple[tuple[str, int], ...]
    top_by_size: tuple[tuple[str, int], ...]


def live_object_census(top_n: int = 20, *, log: bool = True) -> LiveObjectCensus:
    """Census of every object the garbage collector currently tracks — not just
    uncollected cycles (see collect_and_report_types for that). Answers "what's
    actually reachable and heavy right now", which a low/zero
    collect_and_report_types() result can't: gc.collect() only ever frees cyclic
    garbage, never memory some live code is still genuinely holding a reference
    to — the two are different bug classes with different symptoms here.

    Sizes are sys.getsizeof() — SHALLOW, an object's own overhead, not what it
    points to (a dict of huge values looks small; the values themselves show up
    under their own type instead). top_by_count is often more telling than
    top_by_size for exactly that reason. No third-party deep-sizer (e.g.
    pympler) is used, to keep this module dependency-free."""
    objects = gc.get_objects()
    counts: Counter[str] = Counter()
    sizes: Counter[str] = Counter()
    for obj in objects:
        name = type(obj).__name__
        counts[name] += 1
        try:
            sizes[name] += sys.getsizeof(obj)
        except Exception:
            pass
    result = LiveObjectCensus(
        total_objects=len(objects),
        total_bytes_shallow=sum(sizes.values()),
        top_by_count=tuple(counts.most_common(top_n)),
        top_by_size=tuple(sizes.most_common(top_n)),
    )
    if log:
        logger.warning(
            "[GC][census] total_objects=%d total_bytes_shallow=%s top_by_count=%s top_by_size=%s",
            result.total_objects,
            result.total_bytes_shallow,
            result.top_by_count,
            result.top_by_size,
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


def _handle_sigusr2() -> None:
    """SIGUSR2: run both heavier diagnostics back to back — the uncollected-cycle
    type breakdown first (collect_and_report_types), then a full census of every
    reachable object (live_object_census). The first answers "is anything still
    leaking cyclic garbage"; the second answers "what's actually using memory
    right now", regardless of the first's answer."""
    collect_and_report_types()
    live_object_census()


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
      and SIGUSR2 (-> collect_and_report_types + live_object_census), e.g.
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
                active_loop.add_signal_handler(sigusr2, _handle_sigusr2)
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
        try:
            tasks.append(asyncio.create_task(_periodic_loop(interval_s)))
        except RuntimeError as exc:
            # No running event loop (e.g. called from sync startup code) —
            # never fatal, same contract as the signal-registration branch above.
            logger.warning("[fred-core][gc-diagnostics] periodic GC disabled: %s", exc)
        else:
            logger.warning(
                "[fred-core][gc-diagnostics] periodic gc.collect()+malloc_trim() enabled every %ss",
                interval_s,
            )

    return GCDiagnosticsHandle(signals_installed=signals_installed, tasks=tasks)
