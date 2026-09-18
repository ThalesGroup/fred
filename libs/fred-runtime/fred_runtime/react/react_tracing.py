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

"""Shared active parent and tool-span lifecycle for ReAct and Deep tracing."""

from __future__ import annotations

import asyncio
import contextvars
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any

from fred_sdk.contracts.context import PortableContext
from fred_sdk.contracts.runtime import SpanPort, TracerPort

active_agent_span: contextvars.ContextVar[SpanPort | None] = contextvars.ContextVar(
    "active_agent_span", default=None
)

#: Span name for every ReAct tool call, whatever the tool's source. Read by
#: `_TRACE_TOOL_SPAN_NAMES` (v2_runtime/adapters.py), which maps it to a
#: Langfuse `tool` observation and to the `tool` category in the eval read-back.
RUNTIME_TOOL_SPAN_NAME = "v2.react.runtime_tool"


@asynccontextmanager
async def tool_span(
    tracer: TracerPort | None,
    *,
    name: str,
    context: PortableContext,
    attributes: Mapping[str, object],
    input_payload: Any = None,
) -> AsyncIterator[SpanPort | None]:
    """Yield a parented span for caller-owned output, then record status and end it."""

    if tracer is None:
        yield None
        return
    span = tracer.start_span(
        name=name,
        context=context,
        attributes=attributes,
        parent=active_agent_span.get(),
    )
    # A tool span without its arguments and result shows only that a tool ran
    # and how long it took — not enough to tell a bad retrieval from a bad
    # answer, which is the usual reason for opening a trace at all.
    if tracer.captures_content:
        span.set_io(input=input_payload)
    # Nested execution belongs beneath the invoking tool.
    token = active_agent_span.set(span)
    # Set optimistically, before the body runs, so a caller that detects a
    # failure the CM cannot see (a tool returning an `is_error` artifact rather
    # than raising) can overwrite it — last write wins on every backend.
    span.set_attribute("status", "ok")
    try:
        yield span
    except asyncio.CancelledError:
        # Cancellation is a distinct terminal outcome, matching the audit stream.
        span.set_attribute("status", "cancelled")
        raise
    except Exception as exc:
        span.set_attribute("status", "error")
        span.set_attribute("error_type", type(exc).__name__)
        raise
    finally:
        # End before resetting: a token created in another context makes
        # `reset` raise, and an unended span is never exported at all.
        span.end()
        try:
            active_agent_span.reset(token)
        except ValueError:
            active_agent_span.set(None)
