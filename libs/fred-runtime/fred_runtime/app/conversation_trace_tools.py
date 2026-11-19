# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.

"""Bounded structured evidence and in-turn model links for executed tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import TYPE_CHECKING
from uuid import uuid4

from fred_core.conversation_trace import (
    TraceHttpAttempt,
    TraceHttpCompleteness,
    TraceToolCall,
    TraceToolEvidence,
    TraceToolModelLink,
    TraceToolOutcome,
    TraceToolSource,
)
from langchain_core.messages import ToolMessage

from fred_runtime.app.conversation_trace_model import RecordedModelCall, retain_json

if TYPE_CHECKING:
    from fred_runtime.app.conversation_trace_artifacts import HttpTurnBuffer

TOOL_TURN_BYTES = 512 * 1024
_TOOL_FIELD_BYTES = 32 * 1024


@dataclass(slots=True)
class RecordedToolCall:
    buffer: HttpTurnBuffer
    call_id: str | None
    tool_name: str | None
    source: TraceToolSource
    attempt: int
    ref: str = field(default_factory=lambda: uuid4().hex)
    started: float = field(default_factory=monotonic)
    ended: float | None = None
    outcome: TraceToolOutcome = TraceToolOutcome.CANCELLED
    evidence: TraceToolEvidence = field(default_factory=TraceToolEvidence)
    original_output_observed: bool = False
    http_count: int = 0

    def retain(self, field_name: str, value: object) -> None:
        with self.buffer.lock:
            if self.buffer.closed:
                return
            self._retain_locked(field_name, value)

    def _retain_locked(self, field_name: str, value: object) -> None:
        try:
            copied, size, partial = retain_json(
                value, min(self.buffer.tool_remaining, _TOOL_FIELD_BYTES)
            )
            self.buffer.tool_remaining -= size
            self.evidence.partial |= partial
            setattr(self.evidence, field_name, copied)
        except Exception:
            self.evidence.partial = True

    def retain_mcp_result(self, result: object) -> None:
        with self.buffer.lock:
            if not self.buffer.closed:
                self._retain_locked("output", result)
                self.original_output_observed = True

    def finish(self, outcome: TraceToolOutcome, result: object = None) -> None:
        with self.buffer.lock:
            if self.buffer.closed:
                return
            self.outcome = outcome
            self.ended = monotonic()
            # The adapter can retain the MCP result before language conversion.
            if not self.original_output_observed:
                if isinstance(result, ToolMessage):
                    result = (
                        result.artifact
                        if result.artifact is not None
                        else result.content
                    )
                self._retain_locked("output", result)

    def model_links(
        self,
        calls: list[RecordedModelCall],
        *,
        before: float,
    ) -> list[TraceToolModelLink]:
        if self.call_id is None or self.ended is None:
            return []
        requesting: RecordedModelCall | None = None
        for call in calls:
            if call.output is not None and call.started <= self.started:
                for message in call.output.messages:
                    tool_calls = message.get("tool_calls")
                    if isinstance(tool_calls, list) and any(
                        isinstance(item, dict) and item.get("id") == self.call_id
                        for item in tool_calls
                    ):
                        requesting = call
                        break

        links = (
            [TraceToolModelLink(call_id=requesting.call_id, relation="requested")]
            if requesting
            else []
        )
        for call in calls:
            if call.input is None or not self.ended <= call.started < before:
                continue
            for message in reversed(call.input.messages):
                if message.get("tool_call_id") == self.call_id:
                    # Publication owns the closed buffer and uses its remaining budget.
                    self._retain_locked("model_result", message)
                    links.append(
                        TraceToolModelLink(call_id=call.call_id, relation="received")
                    )
                    return links
        return links

    def summary(
        self,
        *,
        stored: bool,
        observed_through_rank: int | None,
        model_calls: list[TraceToolModelLink],
        http_attempts: list[TraceHttpAttempt],
    ) -> TraceToolCall:
        return TraceToolCall(
            ref=self.ref,
            call_id=self.call_id,
            tool_name=self.tool_name,
            source=self.source,
            attempt=self.attempt,
            outcome=self.outcome,
            duration_ms=int(1000 * max(0, (self.ended or monotonic()) - self.started)),
            observed_through_rank=observed_through_rank,
            model_calls=model_calls,
            http_attempts=http_attempts,
            completeness=(
                TraceHttpCompleteness.UNAVAILABLE
                if not stored
                else TraceHttpCompleteness.PARTIAL
                if self.evidence.partial or self.ended is None
                else TraceHttpCompleteness.COMPLETE
            ),
        )
