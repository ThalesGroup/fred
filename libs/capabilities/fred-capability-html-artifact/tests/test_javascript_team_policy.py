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

"""Per-team JavaScript posture: prompt, tool schema, write-time refusal.

The three surfaces that must move together — what the model is told, what the
tool schema advertises, and what the tool accepts — plus the assembly hop that
carries the setting, which this capability is the first to use.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from fred_capability_html_artifact.capability import (
    MAX_ARTIFACT_BYTES,
    HtmlArtifactCapability,
    HtmlArtifactPart,
    HtmlArtifactTeamSettings,
    _HtmlArtifactMiddleware,
    _tool_description,
    html_instructions,
    script_reason,
)
from fred_runtime.capabilities.assembly import build_capability_context
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
)
from fred_sdk.contracts.runtime import RuntimeServices

# Markup the restricted mode must refuse, one entry per execution vector.
SCRIPT_MARKUP = [
    pytest.param("<script>alert(1)</script>", id="script-element"),
    pytest.param("<SCRIPT >alert(1)</SCRIPT>", id="script-element-uppercase"),
    pytest.param("< script>alert(1)</script>", id="script-element-spaced"),
    pytest.param('<button onclick="go()">go</button>', id="inline-handler"),
    pytest.param('<body onload="go()"><p>x</p></body>', id="inline-handler-onload"),
    pytest.param('<a href="javascript:alert(1)">x</a>', id="javascript-url"),
    pytest.param('<a href="java\tscript:alert(1)">x</a>', id="javascript-url-split"),
    pytest.param(
        '<a href="java&#115;cript:alert(1)">x</a>', id="javascript-url-entity"
    ),
    pytest.param(
        '<a href="javascript&colon;alert(1)">x</a>', id="javascript-colon-entity"
    ),
    pytest.param('<iframe srcdoc="<script>x</script>"></iframe>', id="nested-frame"),
]

# Markup that merely LOOKS like script and must still render.
STATIC_MARKUP = [
    pytest.param("<h1>Hello</h1>", id="plain"),
    pytest.param("<div>version=2 button=ok</div>", id="attribute-lookalike"),
    pytest.param("<p>Handlers such as onclick are explained below.</p>", id="prose"),
    pytest.param("<details><summary>More</summary><p>x</p></details>", id="details"),
    pytest.param('<svg viewBox="0 0 8 8"><circle r="4"/></svg>', id="static-svg"),
    # A page ABOUT JavaScript is exactly what a restricted team may legitimately
    # ask for. Refusing it names constructs the page lacks, and the model loops.
    pytest.param("<h2>JavaScript: the basics</h2>", id="prose-javascript-colon"),
    pytest.param("<h2>JavaScript : les bases</h2>", id="prose-javascript-spaced"),
    pytest.param("<p>See javascript: URLs below.</p>", id="prose-javascript-url-word"),
    pytest.param(
        "<pre>&lt;a href=java&#115;cript:example&gt;</pre>", id="escaped-url-tutorial"
    ),
]

# `javascript:` in a value position, which must still be refused.
JAVASCRIPT_URL_MARKUP = [
    pytest.param('<a href="javascript:alert(1)">x</a>', id="double-quoted"),
    pytest.param("<a href='javascript:alert(1)'>x</a>", id="single-quoted"),
    pytest.param("<a href=javascript:alert(1)>x</a>", id="unquoted"),
    pytest.param('<a href = "java\tscript:x">y</a>', id="spaced-and-split"),
]


def _context(allow_javascript: bool) -> CapabilityContext:
    return build_capability_context(
        HtmlArtifactCapability(),
        identity=CapabilityIdentity(user_id="u-1", session_id="s-1"),
        services=RuntimeServices(),
        team_settings={"allow_javascript": allow_javascript},
    )


def _tool(allow_javascript: bool) -> Any:
    """The tool's async callable — `BaseTool` does not type `coroutine`."""

    middleware = _HtmlArtifactMiddleware(_context(allow_javascript))
    return cast(Any, middleware.tools[0])


# --- the setting reaches the capability (the hop no capability had used) ---


@pytest.mark.parametrize("allowed", [True, False])
def test_team_setting_reaches_the_capability_typed(allowed: bool):
    ctx = _context(allowed)

    settings = ctx.team_settings
    assert isinstance(settings, HtmlArtifactTeamSettings)
    assert settings.allow_javascript is allowed


def test_absent_team_settings_denies_javascript():
    """A team with no stored row is restricted, not permissive."""

    ctx = build_capability_context(
        HtmlArtifactCapability(),
        identity=CapabilityIdentity(user_id="u-1", session_id="s-1"),
        services=RuntimeServices(),
        team_settings=None,
    )

    settings = ctx.team_settings
    assert isinstance(settings, HtmlArtifactTeamSettings)
    assert settings.allow_javascript is False


def test_capability_declares_the_team_setting():
    fields = HtmlArtifactCapability.manifest.team_settings_fields

    assert [f.key for f in fields] == ["allow_javascript"]
    assert fields[0].type == "boolean"
    assert fields[0].default is False
    # Optional, or the capability could no longer be granted in one click.
    assert fields[0].required is False


# --- what the model is told ---


def test_restricted_instructions_never_offer_javascript():
    denied = html_instructions(allow_javascript=False).lower()

    assert "not available" in denied
    assert "you may use javascript" not in denied
    # It must say what to do instead, not only what is forbidden.
    assert "static" in denied


def test_permissive_instructions_keep_the_containment_constraints():
    allowed = html_instructions(allow_javascript=True)

    assert "MAY use JavaScript" in allowed
    assert "SELF-CONTAINED" in allowed
    assert "no network calls" in allowed


@pytest.mark.parametrize("allowed", [True, False])
def test_instructions_share_the_invariant_halves(allowed: bool):
    """Opening and closing must not drift between the two variants."""

    text = html_instructions(allow_javascript=allowed)

    assert "you MUST call the 'render_html_artifact' tool" in text
    assert "REVISING IS THE DEFAULT" in text
    assert "no external resources" in text


def test_tool_schema_states_the_posture():
    assert "NOT available" in _tool_description(allow_javascript=False)
    assert "JavaScript is allowed and runs" in _tool_description(allow_javascript=True)


# --- write-time refusal ---


@pytest.mark.asyncio
@pytest.mark.parametrize("html", SCRIPT_MARKUP)
async def test_restricted_team_refuses_script(html: str):
    content, artifact = await _tool(allow_javascript=False).coroutine(
        title="Page", html=html
    )

    assert artifact.is_error is True
    assert not artifact.ui_parts, "a refused page must not be persisted"
    assert "may not run JavaScript" in content
    # The error has to be actionable, or the model retries the same page.
    assert "STATIC" in content


@pytest.mark.asyncio
async def test_restricted_team_refuses_script_in_css():
    _, artifact = await _tool(allow_javascript=False).coroutine(
        title="Page", html="<p>x</p>", css='a { background: url("javascript:x") }'
    )

    assert artifact.is_error is True
    assert not artifact.ui_parts


@pytest.mark.asyncio
@pytest.mark.parametrize("html", STATIC_MARKUP)
async def test_restricted_team_renders_static_markup(html: str):
    content, artifact = await _tool(allow_javascript=False).coroutine(
        title="Page", html=html
    )

    assert artifact.is_error is not True
    assert "rendered (id=" in content
    part = artifact.ui_parts[0]
    assert isinstance(part, HtmlArtifactPart)
    assert part.html == html, "static markup must pass through untouched"


@pytest.mark.asyncio
@pytest.mark.parametrize("html", SCRIPT_MARKUP)
async def test_permissive_team_renders_script_verbatim(html: str):
    """The tool never cleans up: an opted-in team's script is stored as sent."""

    _, artifact = await _tool(allow_javascript=True).coroutine(title="Page", html=html)

    assert artifact.is_error is not True
    assert artifact.ui_parts[0].html == html


@pytest.mark.asyncio
async def test_retry_without_script_succeeds():
    tool = _tool(allow_javascript=False)

    _, refused = await tool.coroutine(title="Tabs", html='<div onclick="t()">Tab</div>')
    _, accepted = await tool.coroutine(
        title="Tabs", html="<details><summary>Tab</summary><p>x</p></details>"
    )

    assert refused.is_error is True
    assert accepted.is_error is not True
    assert accepted.ui_parts


# --- the detector itself ---


@pytest.mark.parametrize("html", SCRIPT_MARKUP)
def test_detector_flags_execution_vectors(html: str):
    assert script_reason(html, "") is not None


@pytest.mark.parametrize("html", STATIC_MARKUP)
def test_detector_leaves_static_markup_alone(html: str):
    assert script_reason(html, "") is None


@pytest.mark.asyncio
async def test_restricted_tool_rejects_oversized_markup_before_scanning(monkeypatch):
    def unexpected_scan(_html: str, _css: str) -> None:
        raise AssertionError("oversized markup must not reach the script scanner")

    monkeypatch.setattr(
        "fred_capability_html_artifact.capability.script_reason", unexpected_scan
    )
    content, artifact = await _tool(allow_javascript=False).coroutine(
        title="Big", html="=" + " " * MAX_ARTIFACT_BYTES
    )

    assert artifact.is_error is True
    assert "too large" in content.lower()


def test_empty_model_team_settings_is_treated_as_denied():
    """Defensive: a context built without this capability's model must not open up."""

    ctx = CapabilityContext(
        identity=CapabilityIdentity(user_id="u-1", session_id="s-1"),
        config=EmptyModel(),
        turn_options=EmptyModel(),
        services=RuntimeServices(),
        team_settings=EmptyModel(),
    )

    assert _HtmlArtifactMiddleware(ctx)._allow_javascript is False


@pytest.mark.asyncio
@pytest.mark.parametrize("html", JAVASCRIPT_URL_MARKUP)
async def test_restricted_team_still_refuses_javascript_urls(html: str):
    """Tightening the prose false positive must not open the real vector."""

    _, artifact = await _tool(allow_javascript=False).coroutine(title="Page", html=html)

    assert artifact.is_error is True
    assert not artifact.ui_parts
