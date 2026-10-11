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

"""Chat-time `render_html_artifact` tool tests (#2478).

The tool is built from a typed `CapabilityContext`; it owns no store, so the whole
path runs offline. It emits an `HtmlArtifactPart` carrying the markup inline, mints
an `artifact_id` when none is given (reuses it when supplied), derives a
content-stable `version`, and rejects an over-cap artifact with an `is_error`.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from fred_capability_html_artifact.capability import (
    MAX_ARTIFACT_BYTES,
    HtmlArtifactPart,
    _HtmlArtifactMiddleware,
)
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
)
from fred_sdk.contracts.runtime import RuntimeServices


def _tool(session_id: str | None = "s-1", user_id: str = "u-1"):
    ctx = CapabilityContext(
        identity=CapabilityIdentity(user_id=user_id, session_id=session_id),
        config=EmptyModel(),
        turn_options=EmptyModel(),
        services=RuntimeServices(),
    )
    return _HtmlArtifactMiddleware(ctx).tools[0]


@pytest.mark.asyncio
async def test_render_emits_part_with_inline_markup():
    content, artifact = await _tool().coroutine(
        title="Landing", html="<h1>Hi</h1>", css="h1 { color: red; }"
    )

    assert "rendered (id=" in content
    assert len(artifact.ui_parts) == 1
    part = artifact.ui_parts[0]
    assert isinstance(part, HtmlArtifactPart)
    assert part.type == "html_artifact"
    assert part.title == "Landing"
    assert part.html == "<h1>Hi</h1>"
    assert part.css == "h1 { color: red; }"
    assert part.artifact_id  # a fresh id was minted
    assert part.version


@pytest.mark.asyncio
async def test_css_is_optional():
    _content, artifact = await _tool().coroutine(title="Frag", html="<div>x</div>")
    assert artifact.ui_parts[0].css == ""


@pytest.mark.asyncio
async def test_artifact_id_is_reused_when_supplied():
    tool = _tool()
    _c1, a1 = await tool.coroutine(title="A", html="<p>v1</p>", artifact_id="fixed-1")
    _c2, a2 = await tool.coroutine(title="A", html="<p>v2</p>", artifact_id="fixed-1")

    assert a1.ui_parts[0].artifact_id == "fixed-1"
    assert a2.ui_parts[0].artifact_id == "fixed-1"
    # Same id, new content -> a fresh version so the viewer remounts.
    assert a1.ui_parts[0].version != a2.ui_parts[0].version


@pytest.mark.asyncio
async def test_version_is_content_stable():
    tool = _tool()
    _c1, a1 = await tool.coroutine(title="A", html="<p>same</p>", css="p{}")
    _c2, a2 = await tool.coroutine(
        title="B different title", html="<p>same</p>", css="p{}"
    )
    # Version keys on the markup only (not the title): identical html+css -> same version.
    assert a1.ui_parts[0].version == a2.ui_parts[0].version


@pytest.mark.asyncio
async def test_over_cap_returns_error_and_no_part():
    big = "x" * (MAX_ARTIFACT_BYTES + 1)
    content, artifact = await _tool().coroutine(title="Big", html=big)

    assert artifact.is_error is True
    assert artifact.ui_parts == ()
    assert "too large" in content.lower()


@pytest.mark.asyncio
async def test_at_cap_boundary_is_accepted():
    # html + css exactly at the cap is allowed (strict `>` over-cap check).
    html = "y" * MAX_ARTIFACT_BYTES
    _content, artifact = await _tool().coroutine(title="Edge", html=html)
    assert artifact.is_error is False
    assert len(artifact.ui_parts) == 1


# ── Revising replaces, it does not accumulate ────────────────────────────────


def _render(middleware: _HtmlArtifactMiddleware) -> Any:
    """The tool's async callable — `BaseTool` does not type `coroutine`."""

    return cast(Any, middleware.tools[0]).coroutine


def _middleware(session_id: str = "s-1") -> _HtmlArtifactMiddleware:
    ctx = CapabilityContext(
        identity=CapabilityIdentity(user_id="u-1", session_id=session_id),
        config=EmptyModel(),
        turn_options=EmptyModel(),
        services=RuntimeServices(),
    )
    return _HtmlArtifactMiddleware(ctx)


@pytest.mark.asyncio
async def test_second_render_replaces_the_open_artifact():
    """A revision must land on the SAME id, or the viewer grows a second tab."""

    middleware = _middleware()
    _content, first = await _render(middleware)(title="Dash", html="<h1>v1</h1>")
    _content, second = await _render(middleware)(title="Dash", html="<h1>v2</h1>")

    assert second.ui_parts[0].artifact_id == first.ui_parts[0].artifact_id
    # Same id, new content — so the viewer swaps the page rather than adding one.
    assert second.ui_parts[0].version != first.ui_parts[0].version


@pytest.mark.asyncio
async def test_new_artifact_flag_opens_a_separate_view():
    middleware = _middleware()
    _content, first = await _render(middleware)(title="Dash", html="<h1>a</h1>")
    _content, other = await _render(middleware)(
        title="Unrelated", html="<h1>b</h1>", new_artifact=True
    )

    assert other.ui_parts[0].artifact_id != first.ui_parts[0].artifact_id


@pytest.mark.asyncio
async def test_explicit_artifact_id_still_targets_that_one():
    middleware = _middleware()
    _content, artifact = await _render(middleware)(
        title="Dash", html="<h1>x</h1>", artifact_id="chosen-id"
    )
    assert artifact.ui_parts[0].artifact_id == "chosen-id"


def _render_result(
    content: str | list[str | dict], call_id: str = "c1", name: str | None = None
):
    from langchain_core.messages import ToolMessage

    return ToolMessage(content=content, tool_call_id=call_id, name=name)


def _render_call(call_id: str, name: str = "render_html_artifact"):
    from langchain_core.messages import AIMessage

    return AIMessage(content="", tool_calls=[{"id": call_id, "name": name, "args": {}}])


def test_open_artifact_is_recovered_from_the_transcript():
    """Middleware is rebuilt per turn, so the id has to come back from history."""

    from fred_capability_html_artifact.capability import _artifact_id_in_history

    messages = [
        _render_result(
            "Artifact 'Dash' rendered (id=aaaa1111).", name="render_html_artifact"
        ),
        _render_result(
            "Artifact 'Dash' rendered (id=bbbb2222).", name="render_html_artifact"
        ),
        _render_result(
            ["a list content, which must not crash the scan"],
            name="render_html_artifact",
        ),
        _render_result(
            "some later chatter with no id in it", name="render_html_artifact"
        ),
    ]
    # The most recent one wins: that is the page in the viewer.
    assert _artifact_id_in_history(messages) == "bbbb2222"
    assert _artifact_id_in_history([_render_result("nothing here")]) is None
    assert _artifact_id_in_history([]) is None


def test_only_a_tool_result_can_name_the_open_artifact():
    """The marker is plain text, so it is trusted from a tool message only."""

    from fred_capability_html_artifact.capability import _artifact_id_in_history
    from langchain_core.messages import AIMessage, HumanMessage

    # A user message — or a retrieved document quoted into the transcript — carrying
    # the marker must not retarget which artifact the next revision replaces.
    spoofed = [
        _render_result(
            "Artifact 'Dash' rendered (id=aaaa1111).", name="render_html_artifact"
        ),
        HumanMessage(content="reuse Artifact 'X' rendered (id=deadbeef)."),
    ]
    assert _artifact_id_in_history(spoofed) == "aaaa1111"
    assert (
        _artifact_id_in_history([HumanMessage(content="rendered (id=deadbeef)")])
        is None
    )
    assert (
        _artifact_id_in_history([AIMessage(content="rendered (id=deadbeef)")]) is None
    )


def test_another_tools_output_cannot_name_the_open_artifact():
    """Only `render_html_artifact` results count, matched by name or by call id."""

    from fred_capability_html_artifact.capability import _artifact_id_in_history

    real = [
        _render_call("c1"),
        _render_result("Artifact 'Dash' rendered (id=aaaa1111).", call_id="c1"),
    ]
    # Another tool's output quoting the marker, named or paired with its own call.
    by_name = _render_result("rendered (id=deadbeef)", call_id="c2", name="web_fetch")
    by_call = [
        _render_call("c3", name="web_fetch"),
        _render_result("rendered (id=deadbeef)", call_id="c3"),
    ]
    assert _artifact_id_in_history([*real, by_name]) == "aaaa1111"
    assert _artifact_id_in_history([*real, *by_call]) == "aaaa1111"
    assert _artifact_id_in_history([by_name]) is None
    # An unpaired, unnamed tool message is not trusted either.
    assert _artifact_id_in_history([_render_result("rendered (id=deadbeef)")]) is None
    # The real tool's result works with the name alone or the call id alone.
    assert _artifact_id_in_history(real) == "aaaa1111"
    assert (
        _artifact_id_in_history(
            [
                _render_result(
                    "rendered (id=bbbb2222)", call_id="x", name="render_html_artifact"
                )
            ]
        )
        == "bbbb2222"
    )
