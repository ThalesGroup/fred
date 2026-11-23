# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.

"""Bounded structured evidence and in-turn model links for executed tools."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from time import monotonic
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from fred_core.conversation_trace import (
    TraceHttpAttempt,
    TraceHttpCompleteness,
    TraceToolCall,
    TraceToolModelLink,
    TraceToolOutcome,
    TraceToolSource,
)
from langchain_core.messages import ToolMessage

from fred_runtime.app.conversation_trace_blocks import TraceBlockRange
from fred_runtime.app.conversation_trace_model import RecordedModelCall, retain_json

if TYPE_CHECKING:
    from fred_runtime.app.conversation_trace_artifacts import HttpTurnBuffer


def _stage_field(value: object, capacity: int) -> tuple[bytes, bool]:
    retained, partial = retain_json(value, capacity)
    return json.dumps(retained, ensure_ascii=False).encode(), partial


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
    partial: bool = False
    original_output_observed: bool = False
    http_count: int = 0
    input_blocks: tuple[TraceBlockRange, ...] | None = None
    output_blocks: tuple[TraceBlockRange, ...] | None = None
    result_model_ref: str | None = None

    async def retain(
        self, field_name: Literal["input", "output"], value: object
    ) -> None:
        writer = self.buffer.block_writer
        if self.buffer.closed:
            return
        try:
            staged = await self.buffer.snapshot_copy(
                _stage_field, value, writer.value_capacity
            )
        except Exception:
            staged = None
        with self.buffer.lock:
            if self.buffer.closed:
                return
            blocks, partial = None, True
            if staged is not None:
                data, partial = staged
                blocks = writer.append(data)
            self.partial |= partial or blocks is None
            self.buffer.incomplete |= self.partial
            if field_name == "input":
                self.input_blocks = blocks
            else:
                self.output_blocks = blocks

    def discard_failed_blocks(self, failed: frozenset[str]) -> None:
        if self.input_blocks is not None and any(
            part.block_id in failed for part in self.input_blocks
        ):
            self.input_blocks = None
            self.partial = True
        if self.output_blocks is not None and any(
            part.block_id in failed for part in self.output_blocks
        ):
            self.output_blocks = None
            self.partial = True

    async def retain_mcp_result(self, result: object) -> None:
        self.original_output_observed = True
        await self.retain("output", result)

    async def finish(self, outcome: TraceToolOutcome, result: object = None) -> None:
        with self.buffer.lock:
            if self.buffer.closed:
                return
            self.outcome = outcome
            self.ended = monotonic()
        # The adapter can retain the MCP result before language conversion.
        if not self.original_output_observed and result is not None:
            if isinstance(result, ToolMessage):
                result = (
                    result.artifact if result.artifact is not None else result.content
                )
            await self.retain("output", result)

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
                    self.result_model_ref = call.ref
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
                if self.partial or self.ended is None
                else TraceHttpCompleteness.COMPLETE
            ),
        )
