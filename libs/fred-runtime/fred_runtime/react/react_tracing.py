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
The ReAct tracing seam: the span a new span attaches to, and the tool-span shape.

`active_agent_span` is whatever span a newly started one should hang under: the
turn's `agent.stream` / `agent.invoke` normally, and the tool span while a tool
call is running. That second case is what makes a sub-agent legible — the child
turn's own root span attaches to the `run_subagent` call that opened it instead
of landing beside its parent as a second root.

`tool_span` is the one place a ReAct tool call becomes a span. Two call sites
open one — `ReActToolBinder` for resolver-bound tools, `ToolObservabilityMiddleware`
for everything else reaching the tool node — and both need identical parenting,
status and end semantics. Full rationale: RUNTIME-EXECUTION-CONTRACT.md §8.65.
"""

from __future__ import annotations

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
    """
    Wrap one tool call in a span parented to the turn's active agent span.

    Yields the span (or None when tracing is off) so the caller can record its
    own output; status, error type and `end()` are handled here.
    """

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
    # A tool that runs a whole agent (`run_subagent`) must contain that agent's
    # spans, not sit next to them — so this span is the parent while it runs.
    token = active_agent_span.set(span)
    try:
        yield span
    except Exception as exc:
        span.set_attribute("status", "error")
        span.set_attribute("error_type", type(exc).__name__)
        raise
    else:
        span.set_attribute("status", "ok")
    finally:
        # End before resetting: a token created in another context makes
        # `reset` raise, and an unended span is never exported at all.
        span.end()
        try:
            active_agent_span.reset(token)
        except ValueError:
            active_agent_span.set(None)
