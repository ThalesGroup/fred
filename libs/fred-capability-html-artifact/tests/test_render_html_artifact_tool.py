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
