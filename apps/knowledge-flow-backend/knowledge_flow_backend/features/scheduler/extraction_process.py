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

"""Run one document's extraction in a child process the activity can terminate.

Why a process and not a thread: extraction offers no place to check a
cancellation flag. docling converts a document in one `convert()` call and
pymupdf4llm in one `to_markdown()`, so a cancelled extraction thread runs to the
end whatever we ask of it. Its Temporal slot is returned meanwhile, and the pod
accepts a new extraction while the previous one still owns the CPU and the
memory. Killing a process is the only thing that actually stops the computation.

Known limitation, not handled here: across a network partition Temporal can hand
one attempt to two workers. Nothing in this module prevents that and nothing
makes it safe — both children extract the same document and write to the same
shared-storage keys, so the surviving output is decided by arrival order and a
reader in between can see one attempt's output mixed with the other's. Excluding
it needs a lease or a fencing token on the document, which this change does not
add.
"""

from __future__ import annotations

import asyncio
import ctypes
import logging
import multiprocessing
import os
import pathlib
import signal
import sys
from collections.abc import Callable
from dataclasses import dataclass
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from typing import Any

from fred_core.documents.document_structures import DocumentMetadata
from temporalio import exceptions

logger = logging.getLogger(__name__)

# How long to wait for a SIGKILLed child and its group to disappear. Only an
# uninterruptible kernel operation can take this long; past it the pod is in
# trouble anyway, and the activity says so rather than reporting itself free.
REAP_TIMEOUT_SECONDS = 10.0

# What the activity keeps for itself, out of its Temporal budget, to stop the
# child and reap it before the server would time the attempt out. Without this
# reserve the activity would still be killing its child when Temporal already
# considers the attempt failed, and the next attempt could start on a busy pod.
SHUTDOWN_RESERVE_SECONDS = 30.0

_POLL_INTERVAL_SECONDS = 0.2
_PR_SET_PDEATHSIG = 1


class ExtractionProcessError(Exception):
    """Extraction failed inside the child process.

    `permanent` carries the child's own verdict: the error type it raised is one
    retrying cannot resolve. An abnormal exit (signal, OOM kill) is never
    permanent — it says nothing about the document.
    """

    def __init__(self, message: str, *, permanent: bool) -> None:
        super().__init__(message)
        self.permanent = permanent


class ExtractionStopUnconfirmed(ExtractionProcessError):
    """The extraction could not be confirmed stopped.

    Says nothing about the document and everything about the pod: only an
    uninterruptible kernel operation survives SIGKILL. Raised in place of
    whatever the activity was about to report — a success, a timeout, even a
    cancellation — because every one of those tells Temporal this worker is free
    to take the next extraction, and it is not.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, permanent=False)


class ExtractionTimeout(Exception):
    """The extraction exceeded the budget the activity derived for it.

    Raised by the activity itself, not by Temporal: an expiring
    `start_to_close_timeout` fails the attempt on the server and reaches the
    worker through a heartbeat response, or not at all. It never stops a
    computation on its own.
    """


@dataclass(frozen=True)
class ExtractionRequest:
    """Everything the child needs, and nothing more.

    Deliberately all plain data: no secret is passed here or on a command line.
    The child inherits the parent's environment, which is where credentials for
    the rich profile's vision calls come from.
    """

    input_path: str
    output_dir: str
    metadata_json: str
    profile: str | None
    config_file: str | None


def _install_parent_death_signal(expected_parent_pid: int) -> None:
    """Ask the kernel to kill this process when its parent dies, and refuse to
    run at all if that parent is already gone.

    The one case the activity cannot cover itself: a worker killed with SIGKILL
    runs no cleanup. prctl is best-effort and Linux-only. The identity check is
    neither, and it is what closes the start-up race — the parent can die between
    the fork and the prctl call, and the signal is then already lost. Comparing
    against the expected parent catches that wherever `getppid() == 1` would not:
    under a subreaper, or in a container whose pid 1 is the worker itself.

    It covers this process only: a descendant it starts does not inherit it,
    which is why the activity signals the whole process group.
    """
    if sys.platform.startswith("linux"):
        try:
            libc = ctypes.CDLL("libc.so.6", use_errno=True)
            if libc.prctl(_PR_SET_PDEATHSIG, signal.SIGKILL, 0, 0, 0) != 0:
                logger.warning("[EXTRACTION][CHILD] could not install PDEATHSIG: errno=%s", ctypes.get_errno())
        except Exception:  # noqa: BLE001 - never let a best-effort guard fail extraction
            logger.warning("[EXTRACTION][CHILD] could not install PDEATHSIG", exc_info=True)
    if os.getppid() != expected_parent_pid:
        logger.warning("[EXTRACTION][CHILD] expected parent %s is already gone; exiting", expected_parent_pid)
        os._exit(1)


def _child_main(request: ExtractionRequest, result_pipe: Connection, parent_pid: int) -> None:
    """Entry point of the extraction process. Module level, so `spawn` can find it."""
    # Lead a process group first, before anything else: until this runs the child
    # is still in the worker's group, and a cancellation landing in that window
    # can only signal the child itself (see `_signal_child`). Narrowing the window
    # is the point of doing it first.
    try:
        os.setsid()
    except OSError:
        logger.warning("[EXTRACTION][CHILD] could not create a process group", exc_info=True)
    _install_parent_death_signal(parent_pid)

    try:
        from knowledge_flow_backend.application_context import ApplicationContext
        from knowledge_flow_backend.common.config_loader import load_configuration
        from knowledge_flow_backend.core.processing_pipeline_manager import ProcessingPipelineManager

        if request.config_file:
            os.environ["CONFIG_FILE"] = request.config_file
        ApplicationContext(load_configuration())
        # A pipeline manager, never an IngestionService: the latter builds the
        # content store and the metadata service, which this process must not
        # open a connection for.
        manager = ProcessingPipelineManager.create_with_default(ApplicationContext.get_instance())
        manager.run_input(
            input_path=pathlib.Path(request.input_path),
            output_dir=pathlib.Path(request.output_dir),
            metadata=DocumentMetadata.model_validate_json(request.metadata_json),
            profile=request.profile,
        )
    except BaseException as exc:  # noqa: BLE001 - the outcome must cross the pipe, whatever it is
        _send_outcome(result_pipe, {"error": f"{type(exc).__name__}: {exc}", "permanent": _is_permanent(exc)})
        os._exit(1)
    _send_outcome(result_pipe, {"error": None, "permanent": False})
    os._exit(0)


def _send_outcome(result_pipe: Connection, outcome: dict[str, Any]) -> None:
    try:
        result_pipe.send(outcome)
        result_pipe.close()
    except Exception:  # noqa: BLE001
        # The parent reads an abnormal exit instead, which is the safe reading.
        logger.warning("[EXTRACTION][CHILD] could not report its outcome", exc_info=True)


def _is_permanent(exc: BaseException) -> bool:
    """Whether retrying this document could ever succeed.

    A missing or undecodable input, or no processor for its type, is settled: the
    next attempt reads the same bytes. Everything else — a storage blip, a model
    endpoint refusing, memory pressure — is left retryable.
    """
    return isinstance(exc, (FileNotFoundError, ValueError, TypeError, NotImplementedError, UnicodeDecodeError))


class _ChildGroup:
    """The child's own process group, latched while it can still be looked up.

    It cannot be read at `start()` — the child creates the group itself — nor
    once the child has been reaped, and both the stop and the descendant sweep
    need it. So it is resolved on every poll and kept the first time it answers.
    """

    def __init__(self, pid: int | None) -> None:
        self._pid = pid
        self.pgid: int | None = None

    def refresh(self) -> None:
        if self.pgid is None and self._pid is not None:
            self.pgid = _own_process_group(self._pid)


async def run_extraction_in_process(
    *,
    request: ExtractionRequest,
    budget_seconds: float,
    heartbeat: Callable[[], None],
    target: Callable[..., None] = _child_main,
    start_method: str = "spawn",
) -> None:
    """Run one extraction in a child process, supervising it without blocking.

    Returns when the extraction succeeded *and* nothing of it is still running.
    Raises `ExtractionProcessError` for a failure inside the child,
    `ExtractionTimeout` when the budget expired or was already spent,
    `ExtractionStopUnconfirmed` when the child could not be confirmed gone, or
    re-raises `asyncio.CancelledError`.

    `heartbeat` is called while waiting: Temporal delivers cancellation through
    heartbeat responses, so a supervisor that stopped beating could not be
    cancelled.

    `target` and `start_method` exist so this supervision can be exercised
    against real processes — including one that starts a descendant — without
    paying a full package import per child. Production always uses the defaults:
    `spawn`, because forking a process holding the worker's event loop, its gRPC
    client and a thread pool copies locks in unknown states.
    """
    if budget_seconds <= 0:
        # Refused before anything exists: this attempt has already spent what it
        # had, and a child started now could only be killed mid-document.
        raise ExtractionTimeout(f"No time left for extraction on this attempt: {budget_seconds:.0f}s once the shutdown reserve is kept.")

    # Typed loosely on purpose: the start method is a parameter, so neither the
    # context class nor the process class is known statically.
    context: Any = multiprocessing.get_context(start_method)
    parent_conn, child_conn = context.Pipe(duplex=False)
    process = context.Process(target=target, args=(request, child_conn, os.getpid()), daemon=False)

    try:
        process.start()
    except BaseException:
        # Cancelled or failed before the process exists: nothing to stop, but the
        # pipe would otherwise leak a file descriptor per attempt.
        parent_conn.close()
        child_conn.close()
        raise
    # The child's copy, kept open in the parent, would stop `poll()` from ever
    # reporting EOF once the child died.
    child_conn.close()

    group = _ChildGroup(process.pid)
    logger.info("[EXTRACTION] child pid=%s budget=%.0fs output=%s", process.pid, budget_seconds, request.output_dir)
    try:
        await _await_process(process, group=group, budget_seconds=budget_seconds, heartbeat=heartbeat)
    except BaseException as exc:
        # Covers cancellation, the local budget expiring, and anything else. The
        # stop has to finish whatever happens: leaving it half-done would return
        # the slot while the computation still holds the pod.
        stopped, cancelled_meanwhile = await _stop_without_abandoning(process, group)
        parent_conn.close()
        _raise_what_the_stop_demands(stopped, cancelled_meanwhile and not isinstance(exc, asyncio.CancelledError))
        raise

    # The child ended by itself, which says nothing about a helper it may have
    # started: that one still holds the CPU the pod is about to hand over.
    stopped, cancelled_meanwhile = await _stop_without_abandoning(process, group)
    outcome = _read_outcome(parent_conn)
    parent_conn.close()
    exit_code = process.exitcode
    process.close()
    _raise_what_the_stop_demands(stopped, cancelled_meanwhile)

    if outcome is None:
        # No verdict crossed the pipe: the child was killed rather than failing in
        # Python. Never permanent — the operating system said nothing about the
        # document.
        raise ExtractionProcessError(
            f"Extraction process ended abnormally (exit code {exit_code}) without reporting an outcome.",
            permanent=False,
        )
    if outcome.get("error"):
        raise ExtractionProcessError(str(outcome["error"]), permanent=bool(outcome.get("permanent")))
    if exit_code != 0:
        raise ExtractionProcessError(f"Extraction process reported success but exited with code {exit_code}.", permanent=False)


def _raise_what_the_stop_demands(stopped: bool, cancelled_meanwhile: bool) -> None:
    """Let the stop overrule the outcome the activity was about to report.

    An unconfirmed stop outranks everything, because every other outcome tells
    Temporal this pod can take the next extraction. A cancellation absorbed while
    stopping is re-raised rather than dropped: the activity was cancelled and has
    to report that, not the result it happened to be carrying.
    """
    if not stopped:
        raise ExtractionStopUnconfirmed("Extraction child not confirmed stopped after SIGKILL; this pod's extraction capacity is not free.")
    if cancelled_meanwhile:
        raise asyncio.CancelledError


def _read_outcome(parent_conn: Any) -> dict[str, Any] | None:
    """The child's verdict, or None when it never sent one.

    A closed pipe polls ready and then raises on read — which is exactly what a
    child killed by the OOM killer leaves behind. Treating that as "no verdict"
    is the whole point: the operating system said nothing about the document.
    """
    try:
        if not parent_conn.poll():
            return None
        outcome = parent_conn.recv()
    except (EOFError, OSError):
        return None
    return outcome if isinstance(outcome, dict) else None


async def _await_process(process: BaseProcess, *, group: _ChildGroup, budget_seconds: float, heartbeat: Callable[[], None]) -> None:
    """Wait for the child without blocking the event loop.

    `process.join()` would block the loop for the whole extraction, which would
    stop every heartbeat on this worker — including those of the other activities
    it is running — and make the worker unable to receive the cancellation this
    supervisor exists to act on.

    The group is resolved before each liveness check and never after: asking
    whether the child is alive is also what reaps it, and a reaped pid has no
    group left to read.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + budget_seconds
    while True:
        group.refresh()
        if not process.is_alive():
            return
        if loop.time() >= deadline:
            raise ExtractionTimeout(f"Extraction exceeded its {budget_seconds:.0f}s budget on this attempt.")
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        heartbeat()


async def _stop_without_abandoning(process: BaseProcess, group: _ChildGroup) -> tuple[bool, bool]:
    """Stop the child without ever walking away from the stop, and without
    leaving it to finish in the background.

    The stop is its own task, awaited through a shield: an activity cancelled
    again while it is already cancelling re-enters the wait instead of returning
    with the computation still running. This returns only once that task is done.

    Reports whether the stop was confirmed, and whether a cancellation landed
    during it.
    """
    stop = asyncio.ensure_future(_stop_group(process, group))
    cancelled = False
    while True:
        try:
            return await asyncio.shield(stop), cancelled
        except asyncio.CancelledError:
            cancelled = True
        except Exception:  # noqa: BLE001 - a stop that failed is a stop we cannot confirm
            logger.error("[EXTRACTION] the stop itself failed; the child cannot be confirmed gone", exc_info=True)
            return False, cancelled


async def _stop_group(process: BaseProcess, group: _ChildGroup) -> bool:
    """SIGKILL what is left of the extraction and wait until none of it answers.

    The group, not the process: an extractor that started a helper leaves it
    running when only the leader is signalled, and that helper still holds the
    resources the pod is about to hand to the next extraction. The group is
    signalled on the normal path too — a child that ended by itself, with a
    success or with an error, can have left one behind.

    SIGKILL with no grace period: extraction has nothing to flush. Its output
    goes to a directory the parent owns and is about to discard, so a polite
    shutdown would only delay the moment the CPU comes back.

    False when the child, or anything in its group, is still there after
    `REAP_TIMEOUT_SECONDS`.
    """
    group.refresh()
    pid = process.pid
    if pid is not None and process.is_alive():
        _signal_child(pid, group.pgid, signal.SIGKILL)
    elif group.pgid is not None:
        # Gone by itself: only what it left behind is signalled. Not the pid —
        # that one has been reaped and could now belong to anything. The group id
        # only becomes reusable once the group is empty, and nothing runs between
        # the reap and this call, so it is still this extraction's.
        _signal_pgid(group.pgid, signal.SIGKILL)

    loop = asyncio.get_running_loop()
    deadline = loop.time() + REAP_TIMEOUT_SECONDS
    while True:
        alive = process.is_alive()
        leftovers = _live_group_members(group.pgid)
        if not alive and not leftovers:
            logger.info("[EXTRACTION] child pid=%s and its process group are gone", pid)
            return True
        if loop.time() >= deadline:
            logger.error(
                "[EXTRACTION] child pid=%s alive=%s, group leftovers=%s after SIGKILL; this pod's extraction capacity is not free",
                pid,
                alive,
                leftovers,
            )
            return False
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)


def _live_group_members(pgid: int | None) -> list[int]:
    """The pids still running in `pgid`, zombies excluded (Linux only).

    Zombies are excluded deliberately: a helper killed here is reparented to pid
    1, and when pid 1 is the worker itself — the usual container layout — nothing
    reaps it. Counting it would make every stop look unconfirmed, and it holds no
    CPU and no memory either way.

    Off Linux this reports nothing: the group is signalled but not confirmed, and
    the workers run on Linux.
    """
    if pgid is None or not sys.platform.startswith("linux"):
        return []
    try:
        entries = os.listdir("/proc")
    except OSError:
        return []
    target = str(pgid).encode()
    members: list[int] = []
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat", "rb") as stat_file:
                # `pid (comm) state ppid pgrp ...`; the name can hold anything,
                # including spaces and parentheses, so it is cut off at the last one.
                fields = stat_file.read().rpartition(b")")[2].split()
        except OSError:
            continue  # exited while being read, which is the answer we wanted
        if len(fields) >= 3 and fields[2] == target and fields[0] != b"Z":
            members.append(int(entry))
    return members


def _signal_child(pid: int, pgid: int | None, sig: int) -> None:
    """Signal the child's own process group — never the worker's.

    A child cancelled between `start()` and its own `setsid()` still belongs to
    the worker's group, and signalling that group would kill the worker, its
    siblings' extractions and its Temporal client. `pgid` is None in exactly that
    window, and the child alone is then enough: it has run none of its own code,
    so it cannot have descendants yet.
    """
    if pgid is not None:
        _signal_pgid(pgid, sig)
        return
    try:
        os.kill(pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _own_process_group(pid: int) -> int | None:
    """The child's own process group, or None when it does not have one yet.

    None also means "still in the worker's group". Signalling that group would
    kill the worker, its siblings' extractions and its Temporal client — so the
    caller signals only the child in that case.
    """
    try:
        pgid = os.getpgid(pid)
    except (ProcessLookupError, PermissionError):
        return None
    return None if pgid == os.getpgid(0) else pgid


def _signal_pgid(pgid: int, sig: int) -> None:
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        pass  # already gone, which is the outcome we wanted
    except PermissionError:
        logger.warning("[EXTRACTION] not allowed to signal process group %s", pgid)
    except OSError:
        logger.warning("[EXTRACTION] could not signal process group %s", pgid, exc_info=True)


async def extract_document(
    *,
    input_path: pathlib.Path,
    output_dir: pathlib.Path,
    metadata: DocumentMetadata,
    profile: Any,
    stage: str,
    started_at: float,
    in_process_fallback: Callable[[], Any],
) -> None:
    """Extract one document — the push and pull paths' single entry point, so
    neither can supervise it differently from the other.

    In a Temporal activity this runs in a killable child process. Outside one it
    does not: the synchronous upload path and library sync call these activity
    functions directly, inside the API process, and there is no worker slot to
    keep honest there and no cancellation to deliver. Spawning an interpreter that
    re-imports docling per uploaded document would be a large, unbounded cost paid
    for nothing.
    """
    from temporalio import activity

    if not activity.in_activity():
        await in_process_fallback()
        return

    request = ExtractionRequest(
        input_path=str(input_path),
        output_dir=str(output_dir),
        metadata_json=metadata.model_dump_json(),
        profile=getattr(profile, "value", profile) if profile is not None else None,
        config_file=os.environ.get("CONFIG_FILE"),
    )
    details = {"stage": stage, "document_uid": metadata.document_uid}

    def _heartbeat() -> None:
        if activity.in_activity():
            activity.heartbeat(details)

    try:
        await run_extraction_in_process(
            request=request,
            budget_seconds=local_budget_seconds(
                activity_timeout_seconds=_attempt_timeout_seconds(),
                elapsed_seconds=asyncio.get_running_loop().time() - started_at,
            ),
            heartbeat=_heartbeat,
        )
    except ExtractionProcessError as exc:
        # Keep the five outcomes apart at the Temporal boundary. A permanent
        # document error must not be retried — the next attempt reads the same
        # bytes — while an abnormal exit says nothing about the document and
        # stays retryable. Collapsing them into one exit code would make every
        # broken file cost six attempts and every transient kill look final.
        if exc.permanent:
            raise exceptions.ApplicationError(str(exc), type="ExtractionPermanentError", non_retryable=True) from exc
        raise


def _attempt_timeout_seconds() -> int:
    """This attempt's Temporal execution budget, read from the activity itself.

    Taken from `activity.info()` rather than plumbed down from the profile, so
    the local budget is derived from the deadline that actually applies to this
    attempt. Outside an activity — the in-process test paths — there is no
    deadline to respect, hence the generous fallback.
    """
    from temporalio import activity

    if not activity.in_activity():
        return 3600
    timeout = activity.info().start_to_close_timeout
    return int(timeout.total_seconds()) if timeout else 3600


def local_budget_seconds(*, activity_timeout_seconds: int, elapsed_seconds: float) -> float:
    """What is left for the extraction itself on this attempt.

    The activity's own deadline, not Temporal's: it starts from the profile's
    timeout, subtracts what this attempt has already spent restoring the input,
    and keeps a reserve to stop the child and reap it. Zero or less means the
    attempt has nothing left to give — the caller refuses it there rather than
    starting a child it could only kill mid-document.
    """
    return float(activity_timeout_seconds) - elapsed_seconds - SHUTDOWN_RESERVE_SECONDS
