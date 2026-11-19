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

"""Bounded diagnostic frame capture on the managed turn clock."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from time import monotonic

from fred_core.conversation_trace import (
    TRACE_MAX_SSE_FRAMES,
    TRACE_SSE_FRAME_BYTES,
    TRACE_SSE_SEGMENT_BYTES,
    TraceSseAvailability,
    TraceSseEnding,
    TraceSseEvent,
    TraceSseKind,
    TraceSseLane,
)
from fred_sdk.contracts.runtime import RuntimeEventKind

_MAX_NUMBER = 2**31 - 1
_LINE_END = re.compile(rb"\r\n?|\n")
_TERMINAL_VALUES = (b"[DONE]", b'"message_stop"', b'"response.completed"')
_VERTEX_FINISH = re.compile(
    rb'"finishReason"\s*:\s*"(?!FINISH_REASON_UNSPECIFIED")[A-Z_]+"'
)
_ANTHROPIC_BLOCK_KINDS = {
    "text": TraceSseKind.TEXT,
    "text_delta": TraceSseKind.TEXT,
    "thinking": TraceSseKind.REASONING,
    "redacted_thinking": TraceSseKind.REASONING,
    "thinking_delta": TraceSseKind.REASONING,
    "signature_delta": TraceSseKind.REASONING,
    "tool_use": TraceSseKind.TOOL,
    "server_tool_use": TraceSseKind.TOOL,
    "input_json_delta": TraceSseKind.TOOL,
}
_OUTGOING_KINDS = {
    RuntimeEventKind.ASSISTANT_DELTA.value: TraceSseKind.TEXT,
    RuntimeEventKind.THOUGHT_START.value: TraceSseKind.REASONING,
    RuntimeEventKind.THOUGHT_DELTA.value: TraceSseKind.REASONING,
    RuntimeEventKind.THOUGHT_END.value: TraceSseKind.REASONING,
    RuntimeEventKind.TOOL_CALL.value: TraceSseKind.TOOL,
    RuntimeEventKind.TOOL_RESULT.value: TraceSseKind.TOOL,
    RuntimeEventKind.STATUS.value: TraceSseKind.STATUS,
    RuntimeEventKind.AWAITING_HUMAN.value: TraceSseKind.STATUS,
    RuntimeEventKind.FINAL.value: TraceSseKind.DONE,
    RuntimeEventKind.NODE_ERROR.value: TraceSseKind.ERROR,
    RuntimeEventKind.EXECUTION_ERROR.value: TraceSseKind.ERROR,
    RuntimeEventKind.EXECUTION_INTERRUPTED.value: TraceSseKind.STATUS,
}
_OUTGOING_ENDINGS = {
    RuntimeEventKind.FINAL.value: TraceSseEnding.COMPLETED,
    RuntimeEventKind.EXECUTION_ERROR.value: TraceSseEnding.FAILED,
    RuntimeEventKind.AWAITING_HUMAN.value: TraceSseEnding.PAUSED,
}


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def provider_kind(frame: bytearray) -> TraceSseKind:
    lines = frame.removeprefix(b"\xef\xbb\xbf").splitlines()
    data = b"\n".join(
        line[5:].removeprefix(b" ") for line in lines if line.startswith(b"data:")
    )
    if data.strip() == b"[DONE]":
        return TraceSseKind.DONE
    try:
        event = _dict(json.loads(data))
    except (ValueError, RecursionError):
        return TraceSseKind.OTHER
    if event.get("error"):
        return TraceSseKind.ERROR
    # The Vertex Gemini adapter consumes the first candidate in each chunk.
    candidates = event.get("candidates")
    if isinstance(candidates, list) and candidates:
        reason = _dict(candidates[0]).get("finishReason")
        if isinstance(reason, str) and reason not in ("", "FINISH_REASON_UNSPECIFIED"):
            return TraceSseKind.DONE
    choices = event.get("choices")
    for choice in choices if isinstance(choices, list) else ():
        delta = _dict(_dict(choice).get("delta"))
        if delta.get("tool_calls") or delta.get("function_call"):
            return TraceSseKind.TOOL
        if delta.get("reasoning_content") or delta.get("reasoning"):
            return TraceSseKind.REASONING
        if delta.get("content"):
            return TraceSseKind.TEXT
    event_type = event.get("type")
    if event_type in ("message_stop", "response.completed"):
        return TraceSseKind.DONE
    if event_type in ("content_block_start", "content_block_delta"):
        field = "content_block" if event_type == "content_block_start" else "delta"
        block_type = _dict(event.get(field)).get("type")
        if isinstance(block_type, str):
            return _ANTHROPIC_BLOCK_KINDS.get(block_type, TraceSseKind.OTHER)
    if event_type in ("message_start", "message_delta", "content_block_stop", "ping"):
        return TraceSseKind.STATUS
    return TraceSseKind.OTHER


@dataclass(slots=True)
class SseBudget:
    started: float = field(default_factory=monotonic)
    offset_ms: int = 0
    frames: int = TRACE_MAX_SSE_FRAMES
    bytes: int = TRACE_SSE_SEGMENT_BYTES
    terminal_bytes: int = TRACE_SSE_FRAME_BYTES

    def at(self, now: float) -> int:
        return min(
            _MAX_NUMBER, self.offset_ms + max(0, int((now - self.started) * 1000))
        )


@dataclass(slots=True)
class RecordedSseLane:
    ref: str
    budget: SseBudget
    started_ms: int
    headers_ms: int | None = None
    headers: dict[str, str] | None = None
    end_ms: int | None = None
    ending: TraceSseEnding = TraceSseEnding.CLOSED
    frames: list[TraceSseEvent] = field(default_factory=list)
    raw: bytearray = field(default_factory=bytearray)
    frame_count: int = 0
    last_event_ms: int | None = None
    gap: tuple[int, int] | None = None
    partial: bool = False
    _pending: bytearray = field(default_factory=bytearray)
    _pending_size: int = 0
    _line_has_data: bool = False
    _pending_cr_at: int | None = None
    _pending_at: int | None = None
    _unfinished_event: TraceSseEvent | None = None
    _terminal_probes: list[tuple[TraceSseEvent | None, bytearray]] = field(
        default_factory=list
    )

    def _add_gap(self, start: int, end: int) -> None:
        if end > start and (
            self.gap is None or end - start > self.gap[1] - self.gap[0]
        ):
            self.gap = (start, end)

    def _record(
        self,
        at: int,
        kind: TraceSseKind,
        size: int,
        data: bytes | bytearray,
    ) -> TraceSseEvent | None:
        self.frame_count = min(_MAX_NUMBER, self.frame_count + 1)
        previous = (
            self.last_event_ms if self.last_event_ms is not None else self.headers_ms
        )
        if previous is not None:
            self._add_gap(previous, at)
        self.last_event_ms = at
        if self.budget.frames <= 0:
            self.partial = True
            return None
        self.budget.frames -= 1
        offset = None
        if 0 < size <= min(self.budget.bytes, TRACE_SSE_FRAME_BYTES) and size == len(
            data
        ):
            offset = len(self.raw)
            self.raw.extend(data)
            self.budget.bytes -= size
        else:
            self.partial = True
        event = TraceSseEvent(at_ms=at, kind=kind, size=size, offset=offset)
        self.frames.append(event)
        return event

    def emitted(self, data: bytes, kind: str, now: float) -> None:
        self.ending = _OUTGOING_ENDINGS.get(kind, self.ending)
        self._record(
            self.budget.at(now),
            _OUTGOING_KINDS.get(kind, TraceSseKind.OTHER),
            min(_MAX_NUMBER, len(data)),
            data,
        )

    def _append(self, data: bytes, start: int, end: int) -> None:
        self._pending_size = min(_MAX_NUMBER, self._pending_size + end - start)
        available = self.budget.bytes if self.budget.frames > 0 else 0
        if self._pending_size <= min(
            TRACE_SSE_FRAME_BYTES, max(available, self.budget.terminal_bytes)
        ):
            self._pending.extend(memoryview(data)[start:end])
        else:
            self._pending.clear()

    def _record_pending(self, at_ms: int, *, complete: bool = True) -> None:
        if self._pending_size:
            event = self._record(
                at_ms, TraceSseKind.OTHER, self._pending_size, self._pending
            )
            if (
                complete
                and (event is None or event.offset is None)
                and 0 < len(self._pending) <= self.budget.terminal_bytes
                and (
                    any(marker in self._pending for marker in _TERMINAL_VALUES)
                    or _VERTEX_FINISH.search(self._pending) is not None
                )
            ):
                self.budget.terminal_bytes -= len(self._pending)
                self._terminal_probes.append((event, self._pending))
                self._pending = bytearray()
            else:
                self._pending.clear()
            if not complete:
                self._unfinished_event = event
            self._pending_size = 0

    def _end_line(self, at_ms: int) -> None:
        if not self._line_has_data:
            self._record_pending(at_ms)
        self._line_has_data = False

    def feed(self, data: bytes, now: float) -> None:
        if not data:
            return
        at = self.budget.at(now)
        self._pending_at = at
        start = 0
        if self._pending_cr_at is not None:
            if data.startswith(b"\n"):
                self._append(data, 0, 1)
                start = 1
            self._end_line(self._pending_cr_at)
            self._pending_cr_at = None
        for match in _LINE_END.finditer(data, start):
            self._line_has_data |= match.start() > start
            self._append(data, start, match.end())
            start = match.end()
            if start == len(data) and match[0] == b"\r":
                self._pending_cr_at = at
            else:
                self._end_line(at)
        if start < len(data):
            self._line_has_data = True
            self._append(data, start, len(data))

    def finish(self, now: float, ending: TraceSseEnding) -> None:
        if self.end_ms is not None:
            return
        at_ms = self.budget.at(now)
        if self._pending_cr_at is not None:
            self._end_line(self._pending_cr_at)
            self._pending_cr_at = None
        if self._pending_size:
            self.partial = True
            self._record_pending(
                self._pending_at if self._pending_at is not None else at_ms,
                complete=False,
            )
        self.end_ms = at_ms
        self.ending = ending

    def prepare_provider(self) -> None:
        """Classify retained original frames after the capture buffer is closed."""
        terminal = False
        for event in self.frames:
            if event.offset is not None:
                event.kind = provider_kind(
                    self.raw[event.offset : event.offset + event.size]
                )
                terminal |= event.kind == TraceSseKind.DONE and (
                    event is not self._unfinished_event
                )
        for event, frame in self._terminal_probes:
            if provider_kind(frame) == TraceSseKind.DONE:
                terminal = True
                if event is not None:
                    event.kind = TraceSseKind.DONE
        self._terminal_probes.clear()
        if self.ending == TraceSseEnding.CLOSED and terminal:
            self.ending = TraceSseEnding.COMPLETED
        if self.ending in (
            TraceSseEnding.CLOSED,
            TraceSseEnding.TIMEOUT,
            TraceSseEnding.TRUNCATED,
            TraceSseEnding.TRANSPORT_ERROR,
        ):
            self.partial = True
            start = (
                self.last_event_ms
                if self.last_event_ms is not None
                else self.headers_ms
            )
            if start is not None and self.end_ms is not None:
                self._add_gap(start, self.end_ms)

    def summary(self, *, stored: bool) -> TraceSseLane:
        return TraceSseLane(
            ref=self.ref,
            started_ms=self.started_ms,
            headers_ms=self.headers_ms,
            headers_available=stored and self.headers is not None,
            end_ms=self.end_ms if self.end_ms is not None else self.started_ms,
            last_event_ms=self.last_event_ms,
            longest_gap=self.gap,
            ending=self.ending,
            availability=(
                TraceSseAvailability.EMPTY
                if self.frame_count == 0 and not self.partial
                else TraceSseAvailability.PARTIAL
                if self.partial or not stored
                else TraceSseAvailability.CAPTURED
            ),
            frame_count=self.frame_count,
            frames=self.frames
            if stored
            else [event.model_copy(update={"offset": None}) for event in self.frames],
        )
