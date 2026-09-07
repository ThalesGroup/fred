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
Regression tests: `ReActToolBinder`'s tracing span reflects a returned
`is_error=True` artifact, not only a raised exception. `_invoke_bound_tool`
used to stamp `status="ok"` on any non-raising return, so a tool that catches
its own failure (the convention every capability tool follows) looked
successful in the trace even though the user saw an error.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from fred_core.portable import Span, Tracer
from fred_runtime.react.react_tool_binding import ReActToolBinder
from fred_runtime.react.react_tool_resolution import (
    FredRuntimeToolSpec,
    ToolPayloadModel,
)
from fred_sdk.contracts.context import (
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
)


class _FakePortable:
    agent_id = "agent-1"
    session_id = "sess-1"
    team_id = "personal"
    baggage: dict[str, object] = {}


class _FakeRuntimeContext:
    pass


class _FakeBinding:
    portable_context = _FakePortable()
    runtime_context = _FakeRuntimeContext()


class _RecordingSpan(Span):
    def __init__(self) -> None:
        self.attributes: dict[str, object] = {}
        self.ended = False

    def set_attribute(self, key: str, value: object) -> None:
        self.attributes[key] = value

    def end(self) -> None:
        self.ended = True


class _RecordingTracer(Tracer):
    def __init__(self) -> None:
        self.spans: list[_RecordingSpan] = []

    def start_span(self, name: str, **kwargs: object) -> _RecordingSpan:
        span = _RecordingSpan()
        self.spans.append(span)
        return span


def _spec_returning(result: ToolInvocationResult) -> FredRuntimeToolSpec:
    async def _invoke(payload: dict[str, object]) -> tuple[str, ToolInvocationResult]:
        return ("rendered", result)

    return FredRuntimeToolSpec(
        runtime_name="test_tool",
        description="test",
        args_schema=ToolPayloadModel,
        tool_ref="test_tool",
        invoke=_invoke,
    )


async def _invoke_via_binder(spec: FredRuntimeToolSpec, tracer: _RecordingTracer):
    binder = ReActToolBinder(
        runtime_tools=(spec,),
        tracer=tracer,
        binding=_FakeBinding(),  # type: ignore[arg-type]
    )
    bound_tool = binder.build_tools()[0]
    coroutine = cast(Any, bound_tool.tool).coroutine
    return await coroutine(payload={})


@pytest.mark.asyncio
async def test_tool_span_reflects_returned_is_error_artifact() -> None:
    """A tool that catches its own failure and returns `is_error=True` (never
    raising) must mark its span `status="error"`, the same as a raised
    exception would."""

    tracer = _RecordingTracer()
    spec = _spec_returning(
        ToolInvocationResult(
            tool_ref="test_tool",
            is_error=True,
            blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text="boom"),),
        )
    )

    await _invoke_via_binder(spec, tracer)

    assert len(tracer.spans) == 1
    assert tracer.spans[0].attributes.get("status") == "error"
    assert tracer.spans[0].attributes.get("error_type") == "tool_error_artifact"
    assert tracer.spans[0].ended is True


@pytest.mark.asyncio
async def test_tool_span_still_ok_on_genuine_success() -> None:
    tracer = _RecordingTracer()
    spec = _spec_returning(
        ToolInvocationResult(
            tool_ref="test_tool",
            blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text="ok"),),
        )
    )

    await _invoke_via_binder(spec, tracer)

    assert len(tracer.spans) == 1
    assert tracer.spans[0].attributes.get("status") == "ok"
