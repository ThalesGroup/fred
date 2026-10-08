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

"""`HtmlArtifactCapability` — agent-generated HTML/CSS/JS with a sandboxed preview.

Why this module exists (HTML-ARTIFACT-CAPABILITY-RFC.md, #2478):
- an agent has no way to produce a *rendered* web page/component; asked for one it
  can only paste HTML/CSS as a code block. This capability gives it one tool,
  `render_html_artifact`, whose output is shown rendered in a viewer beside the
  chat (read-only tabs: Preview / HTML / CSS + download).

Shape (mirrors `writable_document`, minus the store/router — v1 is read-only):
- the contributed `html_artifact` chat part carries the markup INLINE, so no owned
  table is needed (chat ui_parts persist across reload, #2464);
- the chat-time middleware carries the `render_html_artifact` tool AND overlays an
  always-on prompt fragment. The overlay is a `wrap_model_call` hook `tools()`
  cannot express, so the capability is `execution_models=("react",)` and folds the
  tool into the same middleware (like `writable_document` / `ppt_filler`).

Security is a frontend concern (the sandboxed `<iframe srcdoc>` in the viewer,
RFC §4.7); the backend only carries inert markup strings.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from collections.abc import Awaitable, Callable, Sequence
from html.parser import HTMLParser
from typing import Literal, cast

from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityContext,
    CapabilityManifest,
    EmptyModel,
    SidePanelSpec,
)
from fred_sdk.contracts.context import ToolInvocationResult, UiPart
from fred_sdk.contracts.models import FieldSpec
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel

logger = logging.getLogger(__name__)

HTML_ARTIFACT_CAPABILITY_ID = "html_artifact"

# The tool-result `tool_ref` this capability stamps on its artifact.
_TOOL_REF = "html_artifact"

# Max combined html+css size, in bytes. There is no published byte cap for
# Claude.ai artifacts (the effective bound there is the model's per-message
# output-token budget); 256 KB is the engineering equivalent (~one full large
# output message). Over the cap the tool returns an is_error result so the model
# trims instead of persisting a history-bloating blob (RFC §4.4, §9.1).
MAX_ARTIFACT_BYTES = 256 * 1024


class HtmlArtifactPart(BaseModel):
    """The capability's contributed `html_artifact` chat part (RFC §4.4).

    The markup travels INLINE on the part (like `WritableDocumentPart.content_md`):
    v1 is read-only with no owned table, and chat `ui_parts` persist across reload
    (#2464), so the artifact survives without a capability store. `html` and `css`
    stay separate to feed the viewer's HTML/CSS tabs; the frontend composes them
    for the Preview iframe and the download.
    """

    type: Literal["html_artifact"] = "html_artifact"
    artifact_id: str
    title: str
    html: str
    css: str
    # Per-content hash; a re-render with identical markup keeps the same version
    # (no needless viewer remount), any change bumps it (the pane remounts on it).
    version: str


class HtmlArtifactTeamSettings(BaseModel):
    """Per-team enablement settings (RFC §8.2) — the JavaScript posture.

    Running model-authored script is an operator decision taken team by team, so
    it defaults to off: a team gets it only once an admin turns it on.
    """

    allow_javascript: bool = False


# Non-negotiable behavioral fragment delivered whenever the capability is active
# (same delivery path as writable_document's `_WRITE_INSTRUCTIONS` and the MCP
# capabilities' `agent_instructions`). Without it, models paste HTML/CSS inline in
# the chat instead of calling the tool.
#
# Two variants, assembled from shared halves so the parts that are identical in
# both modes cannot drift apart. Which one is delivered follows the team setting.
_INSTRUCTIONS_OPENING = (
    "HTML ARTIFACT: when the user asks — in any wording or language — to build, "
    "create, design, or show a web page, HTML page, component, section, layout, "
    "mockup, or styled HTML, you MUST call the 'render_html_artifact' tool with "
    "the HTML and (optionally) the CSS; never paste the HTML/CSS as a code block "
    "in the chat. A rendered preview opens in a viewer beside the chat where the "
    "user can see the result, read the source, and download it. "
)

_INSTRUCTIONS_JS_ALLOWED = (
    "You MAY use "
    "JavaScript for interaction — tabs, accordions, animations, charts drawn on a "
    "canvas — inline in a <script> element or as event handlers. Everything must "
    "be SELF-CONTAINED: no external resources at all (no remote scripts, "
    "stylesheets, fonts, or images) and no network calls (fetch, XHR and "
    "WebSocket are blocked and will fail) — inline any image as a data: URI and "
    "any data your script needs as a literal. The page runs in an isolated frame, "
    "so localStorage, sessionStorage and cookies are unavailable and throw — hold "
    "state in JavaScript variables. `eval` and `new Function` are blocked and "
    'throw, and `setTimeout("string")` silently never runs — write real '
    "functions instead. "
)

# The restricted half. It states the refusal as a property of the page rather
# than a rule to remember, because a model that merely "avoids" script still
# reaches for an onclick when the user asks for tabs.
_INSTRUCTIONS_JS_DENIED = (
    "JavaScript is NOT available here: this team may not run script. A page "
    "containing a <script> element, an inline event handler attribute (onclick, "
    "onload, …) or a javascript: URL is REFUSED by the tool — write a fully "
    "STATIC page instead. Use CSS for whatever movement or state the design "
    "needs (transitions, :hover, :target, :checked with a hidden input) and lay "
    "out the content so it reads without interaction — sections one after "
    "another rather than tabs, details/summary rather than a scripted "
    "accordion. Do not offer the user an interactive version. Everything must "
    "be SELF-CONTAINED: no external resources at all (no remote scripts, "
    "stylesheets, fonts, or images) — inline any image as a data: URI. "
)

_INSTRUCTIONS_CLOSING = (
    "Keep the CSS in the css argument, "
    "not in a <style> tag. REVISING IS THE DEFAULT: when the user asks to change, "
    "fix, restyle, extend or shorten the page you just produced, call the tool "
    "again with no artifact_id — it REPLACES that page in the viewer instead of "
    "opening a second one. Pass new_artifact=true only for a page that has nothing "
    "to do with the previous one. In the chat, reply only with a short summary of "
    "what you built or changed."
)

_HTML_INSTRUCTIONS_JS_ALLOWED = (
    _INSTRUCTIONS_OPENING + _INSTRUCTIONS_JS_ALLOWED + _INSTRUCTIONS_CLOSING
)
_HTML_INSTRUCTIONS_JS_DENIED = (
    _INSTRUCTIONS_OPENING + _INSTRUCTIONS_JS_DENIED + _INSTRUCTIONS_CLOSING
)


def html_instructions(allow_javascript: bool) -> str:
    """The prompt fragment for this team's JavaScript posture."""

    return (
        _HTML_INSTRUCTIONS_JS_ALLOWED
        if allow_javascript
        else _HTML_INSTRUCTIONS_JS_DENIED
    )


# The tool announces its id in its own result text, which is the only trace that
# outlives a turn: capability middleware is rebuilt per turn, so there is no memory
# to keep it in. Reading it back from the transcript is what lets a revision target
# the open artifact without the model having to remember an id. Matched against tool
# messages only — see `_artifact_id_in_history`.
_RENDERED_ID = re.compile(r"rendered \(id=([0-9a-f]+)\)")


def _artifact_id_in_history(messages: Sequence[object]) -> str | None:
    """The most recently rendered artifact id in this conversation, if any.

    Only TOOL messages are scanned. The marker is text, and a user message, a
    retrieved document or another tool's output could carry the same wording and
    retarget which artifact a revision replaces.
    """

    for message in reversed(list(messages)):
        if getattr(message, "type", None) != "tool":
            continue
        content = getattr(message, "content", None)
        if not isinstance(content, str):
            continue
        found = _RENDERED_ID.findall(content)
        if found:
            return found[-1]
    return None


# Markup that would execute script. Used ONLY to REFUSE a render for a team that
# may not run script — never to clean one up, so over-matching is the safe side
# and is deliberate: the model simply rewrites the page. The security boundary is
# the viewer's empty sandbox, not this pattern.
_SCRIPT_MARKERS = (
    # `<script` in any casing, and any tag whose name merely starts with it.
    re.compile(r"<\s*script", re.IGNORECASE),
    # Inline handler attributes: `on<name>` followed by `=`. Requires a preceding
    # separator so words like "version=" or "button=" cannot match.
    re.compile(r"[\s\"'/]on[a-z]+\s*=", re.IGNORECASE),
    # `javascript:` URLs, whitespace-obfuscated spellings included. Anchored to a
    # value position (`href="…"`, `url(…)`) rather than matched anywhere: the bare
    # word appears in ordinary prose, and a page ABOUT JavaScript is exactly the
    # kind of static page a restricted team may legitimately ask for. Refusing it
    # would name constructs the page does not have, and the model would loop.
    re.compile(
        r"""(?:=|\()[\s"']*j\s*a\s*v\s*a\s*s\s*c\s*r\s*i\s*p\s*t\s*:""",
        re.IGNORECASE,
    ),
    # `<svg>`'s scripting vectors and `<iframe srcdoc>` reintroduce execution
    # without the word "script" appearing as a tag name.
    re.compile(r"<\s*(?:iframe|object|embed)", re.IGNORECASE),
)


class _ScriptUrlParser(HTMLParser):
    """Detect URL attributes after HTML entity decoding, as a browser would."""

    def __init__(self) -> None:
        super().__init__()
        self.found = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if any(
            name in {"href", "xlink:href", "formaction"}
            and value is not None
            and re.match(
                r"^\s*j\s*a\s*v\s*a\s*s\s*c\s*r\s*i\s*p\s*t\s*:", value, re.IGNORECASE
            )
            for name, value in attrs
        ):
            self.found = True


def script_reason(html: str, css: str) -> str | None:
    """Why this page would execute script, or None when it is static.

    CSS is checked too: `url("javascript:…")` and behaviour-bearing values have
    carried execution historically, and a static page has no reason to hold one.
    """

    for pattern in _SCRIPT_MARKERS:
        if pattern.search(html) or pattern.search(css):
            return pattern.pattern
    if "&" in html:
        parser = _ScriptUrlParser()
        parser.feed(html)
        if parser.found:
            return "decoded javascript: URL"
    return None


def _artifact_version(html: str, css: str) -> str:
    """Deterministic per-content version (drives the viewer's remount key)."""

    digest = hashlib.sha256()
    digest.update(html.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(css.encode("utf-8"))
    return digest.hexdigest()[:16]


# The tool schema the model sees. Same two-variant shape as the prompt fragment
# above and for the same reason: the posture must be stated where the model reads
# the contract, not only in the overlay.
_TOOL_DESC_OPENING = (
    "Render an HTML/CSS artifact in a viewer beside the chat.\n\n"
    "Use this whenever the user asks for a web page, component, section, "
    "layout, mockup, or any styled HTML, so the RESULT is shown rendered "
    "(not as a code block) and the user can read the source and download it.\n\n"
)

_TOOL_DESC_JS_ALLOWED = (
    "JavaScript is allowed and runs: use it for tabs, accordions, animations, "
    "or canvas drawing. It must be inline (a <script> element or event "
    "handlers) and the artifact must be self-contained — no external "
    "resources and no network calls, which are blocked and will fail. Inline "
    "images as data: URIs and any data your script needs as a literal. The "
    "page runs in an isolated frame, so localStorage, sessionStorage and "
    "cookies are unavailable and throw — keep state in JS variables. `eval` "
    "and `new Function` are blocked; pass real functions, never code strings. "
)

_TOOL_DESC_JS_DENIED = (
    "JavaScript is NOT available for this team and the call is REFUSED if the "
    "page contains a <script> element, an inline event handler attribute or a "
    "javascript: URL. Produce a static page: CSS for any movement or state "
    "(transitions, :hover, :target, :checked), details/summary instead of a "
    "scripted accordion, stacked sections instead of tabs. The artifact must "
    "be self-contained — no external resources; inline images as data: URIs. "
)

_TOOL_DESC_CLOSING = (
    "Put the CSS in the css argument (not in a <style> tag). The html may be a "
    "full document (<!doctype html>...) or a bare fragment (e.g. one <div>). "
    "REVISING IS THE DEFAULT. Call this with no artifact_id to REPLACE the "
    "page currently in the viewer — that is what a request to change, fix, "
    "restyle or extend it means. Set new_artifact=true only for a page "
    "unrelated to the previous one, which opens a second view alongside it. "
    "Pass an explicit artifact_id only to target one specific page when "
    "several are open."
)


def _tool_description(allow_javascript: bool) -> str:
    """The `render_html_artifact` schema description for this team's posture."""

    middle = _TOOL_DESC_JS_ALLOWED if allow_javascript else _TOOL_DESC_JS_DENIED
    return _TOOL_DESC_OPENING + middle + _TOOL_DESC_CLOSING


class _HtmlArtifactMiddleware(AgentMiddleware):
    """The html_artifact runtime half: the render tool + the always-on prompt fragment.

    ReAct-only: the prompt overlay (`awrap_model_call`) is a hook `tools()` cannot
    express, so the tool is carried here too and the capability declares
    `execution_models=("react",)` (mirrors `writable_document`). Identity is closed
    over from `ctx.identity` and never enters the tool schema (RFC §3.5).
    """

    def __init__(self, ctx: CapabilityContext[EmptyModel, EmptyModel]) -> None:
        super().__init__()
        session_id = ctx.identity.session_id
        # An admin decision, resolved per turn: the middleware is rebuilt each
        # turn, so a revocation reaches the next one without any cache to clear.
        settings = ctx.team_settings
        self._allow_javascript = bool(
            getattr(settings, "allow_javascript", False) is True
        )
        # The artifact a revision should replace. Recovered from the transcript on
        # each model call (see `awrap_model_call`) and advanced after every render,
        # so a second call in the same turn revises rather than piling up.
        self._open_artifact_id: str | None = None

        @tool(
            "render_html_artifact",
            response_format="content_and_artifact",
            # The schema the model sees must state the posture too: a team that
            # cannot run script should never be offered it in the tool contract
            # and then refused at call time.
            description=_tool_description(self._allow_javascript),
        )
        async def render_html_artifact(
            title: str,
            html: str,
            css: str = "",
            artifact_id: str | None = None,
            new_artifact: bool = False,
        ) -> tuple[str, ToolInvocationResult]:
            """Render an HTML/CSS artifact in a viewer beside the chat.

            The description the MODEL reads is `_tool_description(...)`, passed to
            the decorator above: it varies with the team's JavaScript posture, so
            this docstring is for humans only and deliberately says nothing about
            what is or is not allowed.
            """

            size = len(html.encode("utf-8")) + len(css.encode("utf-8"))
            if size > MAX_ARTIFACT_BYTES:
                message = (
                    f"The artifact is too large ({size} bytes). The limit is "
                    f"{MAX_ARTIFACT_BYTES} bytes ({MAX_ARTIFACT_BYTES // 1024} KB) "
                    "of HTML + CSS combined. Trim the content and call the tool "
                    "again."
                )
                return (
                    message,
                    ToolInvocationResult(tool_ref=_TOOL_REF, is_error=True),
                )

            # Bound untrusted input before scanning it, including for restricted
            # teams. A long rejected page must not monopolize the event loop.
            if not self._allow_javascript:
                matched = script_reason(html, css)
                if matched is not None:
                    logger.info(
                        "[HTML_ARTIFACT][TOOL] session=%s refused: script in a "
                        "team without allow_javascript (pattern=%s)",
                        session_id,
                        matched,
                    )
                    message = (
                        "This team may not run JavaScript, and the page you sent "
                        "contains script (a <script> element, an inline event "
                        "handler attribute, a javascript: URL, or an embedded "
                        "frame). Nothing was rendered. Send the page again as a "
                        "STATIC document: use CSS for movement or state "
                        "(transitions, :hover, :target, :checked with a hidden "
                        "input), details/summary instead of a scripted accordion, "
                        "and stacked sections instead of tabs."
                    )
                    return (
                        message,
                        ToolInvocationResult(tool_ref=_TOOL_REF, is_error=True),
                    )

            # Replace by default: an omitted id means "the page already in the
            # viewer", never "make another one". Only an explicit new_artifact — or
            # having nothing open yet — mints a fresh id.
            if new_artifact:
                aid = uuid.uuid4().hex
            else:
                aid = artifact_id or self._open_artifact_id or uuid.uuid4().hex
            self._open_artifact_id = aid
            part = HtmlArtifactPart(
                artifact_id=aid,
                title=title,
                html=html,
                css=css,
                version=_artifact_version(html, css),
            )
            logger.info(
                "[HTML_ARTIFACT][TOOL] session=%s artifact_id=%s title=%r "
                "html_len=%d css_len=%d",
                session_id,
                aid,
                title[:80],
                len(html),
                len(css),
            )
            artifact = ToolInvocationResult(
                tool_ref=_TOOL_REF,
                ui_parts=(cast(UiPart, part),),
            )
            return f"Artifact '{title}' rendered (id={aid}).", artifact

        self.tools: Sequence[BaseTool] = [render_html_artifact]

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """Overlay the always-on html-artifact instructions per model call.

        Mirrors `_McpInstructionsMiddleware`: the static composed system prompt
        reaches `create_agent`; this overlay keeps the "use render_html_artifact,
        keep it self-contained" reminder alive across turns without persisting it.
        """

        self._open_artifact_id = _artifact_id_in_history(request.messages)
        overlay = html_instructions(self._allow_javascript)
        if self._open_artifact_id:
            overlay += (
                f" The page currently in the viewer is {self._open_artifact_id}; "
                "calling the tool without an artifact_id replaces it."
            )
        base = request.system_prompt or ""
        merged = f"{base}\n\n{overlay}" if base else overlay
        request = request.override(system_message=SystemMessage(content=merged))
        return await handler(request)


class HtmlArtifactCapability(AgentCapability[EmptyModel, EmptyModel, EmptyModel]):
    """Render agent-generated HTML/CSS/JS in a sandboxed viewer beside the chat.

    No agent-creation config, no upload slots, no owned table, no router (v1 is
    read-only; the markup rides inline on the chat part). The whole feature is the
    contributed `html_artifact` chat part, the viewer side panel, and the chat-time
    middleware (the `render_html_artifact` tool + the always-on prompt fragment).
    """

    manifest = CapabilityManifest(
        # Bumped for the first team setting: `version` is the stored-config
        # schema version and half the cache key for computed surfaces.
        version="0.2.0",
        id=HTML_ARTIFACT_CAPABILITY_ID,
        name="capability.html_artifact.name",
        description="capability.html_artifact.description",
        icon="code",
        chat_parts=[HtmlArtifactPart],
        side_panels=[SidePanelSpec(widget="html_artifact_pane")],
        # Optional and defaulted, so the capability stays grantable to a team in
        # one click; leaving it unset is the restricted posture.
        team_settings_fields=[
            FieldSpec(
                key="allow_javascript",
                type="boolean",
                title="capability.html_artifact.teamSettings.allow_javascript.title",
                description="capability.html_artifact.teamSettings.allow_javascript.description",
                default=False,
            )
        ],
        # CAPAB-02: the `awrap_model_call` prompt overlay is a ReAct-only hook
        # `tools()` cannot express, so the tool is carried by the middleware and
        # the capability is explicitly ReAct-only rather than silently
        # contributing zero tools to a Graph agent that selects it.
        execution_models=("react",),
    )
    ConfigModel = EmptyModel
    TeamSettingsModel = HtmlArtifactTeamSettings

    def middleware(
        self, ctx: CapabilityContext[EmptyModel, EmptyModel]
    ) -> list[AgentMiddleware]:
        return [_HtmlArtifactMiddleware(ctx)]
