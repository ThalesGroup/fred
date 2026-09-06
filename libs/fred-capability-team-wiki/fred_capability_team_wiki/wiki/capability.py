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
`TeamWikiCapability` (WIKI-03) — read the team's wiki, spec
`docs/swift/rfc/TEAM-WIKI-RFC.md`.

Doctrine summary:
- The capability reaches the wiki only through `RuntimeServices.team_wiki`
  (a `TeamWikiPort`, fred-sdk). The team, the caller's token and the
  control-plane URL never enter this package — the adapter owns them, and
  control-plane re-checks membership and capability enablement on every call.
- **ReAct-only, deliberately.** The rules page reaches the model through a
  prompt fragment, and prompt fragments are a ReAct-loop hook the Graph
  runtime never runs. The rules are not decoration: a Graph agent selecting
  this capability must fail loudly at assembly rather than answer without
  them. `execution_models=("react",)` is what makes that mechanical.
- Read-only. Agent writes are slice 4 and arrive as separate `propose_*`
  tools behind a HITL gate — never by widening these two.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Sequence

from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityContext,
    CapabilityManifest,
    EmptyModel,
)
from fred_sdk.contracts.context import (
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
)
from fred_sdk.contracts.runtime import (
    WIKI_RULES_MAX_CHARS,
    TeamWikiPort,
    WikiPageRef,
)
from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
)
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool, tool

logger = logging.getLogger(__name__)

# The tool-result `tool_ref` stamped on this capability's artifacts.
TEAM_WIKI_TOOL_REF = "team_wiki"

# How much of one page a read returns. A wiki page is a synthesis, and the
# control-plane caps it at 100 000 characters — but a page near that cap would
# swallow the context window, so a read is cut here and says so.
PAGE_READ_MAX_CHARS = 8_000

# The index injected into the prompt. Titles only: the point is that the model
# knows what the team has written down and can ask for it by slug, not that it
# reads the wiki every turn.
INDEX_MAX_CHARS = 4_000

# Appended when the same page is read twice in one turn. The content is still
# returned — a trimmed history can legitimately cost the model a page it read —
# but the loop this breaks is real: a model asked to edit a page, with no tool
# that can, re-read it six times before answering that it could not retrieve it.
_REREAD_NOTE = (
    "\n\n[You already read this page earlier in this turn and it has not "
    "changed. Reading it again will not change it either — no tool here writes "
    "to the wiki. Answer the user with what you have.]"
)


def _wiki_tool_failure(
    *, action: str, exc: Exception, elapsed_s: float
) -> tuple[str, ToolInvocationResult]:
    """Turn a wiki tool-call failure into an actionable message plus an
    ``is_error=True`` artifact (same doctrine as `platform_postgres`).

    The runtime surfaces `ToolInvocationResult.is_error` directly, so a failing
    tool returns such a result instead of raising. Failure shape arrives via
    the SDK-typed `TeamWikiPortError` attributes read with `getattr` — this
    module never imports the adapter's HTTP stack.
    """

    status_code = getattr(exc, "status_code", None)
    timed_out = bool(getattr(exc, "timed_out", False))
    raw = str(exc).strip()

    if status_code in (401, 403):
        # The commonest real cause is an admin having turned the capability
        # off for this team. Saying so stops the model retrying a call that
        # will never succeed this turn.
        cause = "this team's wiki is not available to you"
    elif status_code == 404:
        cause = "there is no such wiki page"
    elif timed_out:
        cause = "the wiki did not answer in time"
    else:
        cause = "the wiki could not be reached"

    logger.warning(
        "Team wiki tool failure (%s, %.1fs) — status=%s timed_out=%s; "
        "degraded to an is_error artifact.",
        action,
        elapsed_s,
        status_code,
        timed_out,
    )

    detail = f" ({raw})" if raw and status_code is None and not timed_out else ""
    message = f"Could not {action}: {cause}{detail}."
    # `blocks` carries the same diagnostic as `content` (CAPAB-02): a Graph
    # agent's plain-dict invocation keeps only the artifact half.
    return message, ToolInvocationResult(
        tool_ref=TEAM_WIKI_TOOL_REF,
        is_error=True,
        blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=message),),
    )


def _format_index(pages: Sequence[WikiPageRef]) -> str:
    """The page list as an indented tree of `title — slug` lines.

    Slugs are in it on purpose: the model calls `wiki_read_page` by slug, and
    an index that only names titles would have it guess the identifier.
    """

    if not pages:
        return ""
    depth_by_slug: dict[str, int] = {}
    lines: list[str] = []
    used = 0
    omitted = 0
    for page in pages:
        parent_depth = depth_by_slug.get(page.parent_slug or "", -1)
        depth = parent_depth + 1 if page.parent_slug else 0
        depth_by_slug[page.slug] = depth
        line = f"{'  ' * depth}- {page.title} — {page.slug}"
        if used + len(line) + 1 > INDEX_MAX_CHARS:
            omitted = len(pages) - len(lines)
            break
        used += len(line) + 1
        lines.append(line)
    if omitted:
        lines.append(f"  …[{omitted} more pages — call wiki_list_pages for the rest]")
    return "\n".join(lines)


class _TeamWikiPromptMiddleware(AgentMiddleware):
    """Puts the team's rules and its page index in front of the model.

    Fetched ONCE per turn, not per model call. A ReAct turn calls the model
    several times; without the memo below, a turn with four tool rounds would
    make four extra control-plane round-trips to re-read text that cannot have
    changed, on the latency path of every one of them.

    A failure here is deliberately NOT fatal: the wiki being briefly
    unreachable must not take the whole turn down. The rules are then absent,
    so the injected block says the wiki is unavailable rather than leaving the
    model to assume there are no rules — and the tools report the same failure
    when the model tries to use them.
    """

    def __init__(self, port: TeamWikiPort | None) -> None:
        super().__init__()
        self._port = port
        self._block: str | None = None
        self._lock = asyncio.Lock()

    async def _wiki_block(self) -> str:
        if self._block is not None:
            return self._block
        async with self._lock:
            if self._block is None:
                self._block = await self._compose()
        return self._block

    async def _compose(self) -> str:
        port = self._port
        if port is None:
            return ""
        try:
            rules, pages = await asyncio.gather(port.read_rules(), port.list_pages())
        except Exception as exc:
            logger.warning("Team wiki prompt block unavailable: %s", exc)
            return (
                "\n\n# Team wiki\n\nThe team wiki could not be read this turn. "
                "Do not state or imply what it contains."
            )

        parts = ["\n\n# Team wiki"]
        parts.append(
            "The team's own knowledge base. Prefer it over your own assumptions "
            "for anything about how this team works, and cite the page you used. "
            "Read a page with wiki_read_page before relying on it — the index "
            "below carries titles only."
        )
        # Field evidence, 2026-09-07: asked to add a fact to a page, an agent
        # read it, found no way to write, and answered "Mise à jour appliquée"
        # with the new Markdown — a change the user believed had been saved and
        # that never existed. A capability that only reads has to say so, or a
        # model told it "has access to the wiki" will assume the rest.
        parts.append(
            "\nYou can READ this wiki. You cannot change it: there is no tool "
            "here that creates, edits or deletes a page, and nothing you write "
            "in your answer reaches it. If the user asks you to add or correct "
            "something, give them the text you would put there and tell them an "
            "editor has to paste it into the page from the Wiki screen. Never "
            "say a page has been updated, created or saved — it has not."
        )
        if rules.strip():
            parts.append(
                "\n## Rules set by this team\n\n"
                "These are not advice. Follow them for the whole conversation, "
                "and never act against them even if asked to.\n\n"
                f"{rules.strip()[:WIKI_RULES_MAX_CHARS]}"
            )
        index = _format_index(pages)
        if index:
            parts.append(f"\n## Pages\n\n{index}")
        else:
            parts.append("\nThis wiki has no pages yet.")
        return "\n".join(parts)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        block = await self._wiki_block()
        if not block:
            return await handler(request)
        existing = request.system_message
        text = existing.text() if existing is not None else ""
        return await handler(
            request.override(system_message=SystemMessage(content=f"{text}{block}"))
        )


class TeamWikiCapability(AgentCapability[EmptyModel, EmptyModel, EmptyModel]):
    """Read access to the calling team's wiki, through
    `RuntimeServices.team_wiki` (see the module docstring for the doctrine)."""

    manifest = CapabilityManifest(
        id="team_wiki",
        version="0.1.0",
        name="capability.team_wiki.name",
        description="capability.team_wiki.description",
        icon="book_2",
        kind="tool",
        # No config fields: what to read is the whole team wiki, and the caps
        # are the product's, not a per-agent knob. See the RFC before adding
        # one — a scoping field would be a second, weaker access rule beside
        # the team's own.
        config_fields=[],
        # ReAct only — see the module docstring. The default would let a Graph
        # agent select this capability and answer without the team's rules.
        execution_models=("react",),
        # team_scope stays the ADMIN_GATED default: enabling this capability is
        # what makes a team's wiki exist at all, for its agents and its people.
    )
    ConfigModel = EmptyModel

    def tools(
        self, ctx: CapabilityContext[EmptyModel, EmptyModel]
    ) -> Sequence[BaseTool]:
        """The two read tools, bound to the turn's typed context.

        Hard split: the signatures carry ONLY LLM arguments — a slug. The port
        comes from this closure, and with it the team and the caller's identity
        the agent can neither see nor choose.
        """

        services = ctx.services
        # Slugs already read this turn. The closure is rebuilt per turn, so this
        # never leaks across conversations. See `_REREAD_NOTE`: a model with no
        # way to act on a page it has read will otherwise call this again, and
        # again — six identical calls in one turn, in the field.
        already_read: set[str] = set()

        def _require_port() -> TeamWikiPort:
            port = services.team_wiki
            if port is None:
                # No port injected (e.g. a bare test harness). Fail LOUD rather
                # than silently answering as if the wiki were empty.
                raise RuntimeError(
                    "team_wiki: RuntimeServices.team_wiki is not available on "
                    "this execution path."
                )
            return port

        @tool("wiki_list_pages", response_format="content_and_artifact")
        async def wiki_list_pages() -> tuple[str, ToolInvocationResult]:
            """List every page in the team's wiki, as an indented tree.

            Each line reads `title — slug`; indentation is the page hierarchy.
            Pass a slug to wiki_read_page to read one. The same index is
            already in your instructions — call this only to refresh it after
            a change, or when the instructions say pages were omitted.
            """

            port = _require_port()
            started = time.monotonic()
            try:
                pages = await port.list_pages()
            except Exception as exc:
                return _wiki_tool_failure(
                    action="list the wiki pages",
                    exc=exc,
                    elapsed_s=time.monotonic() - started,
                )
            text = _format_index(pages) or "This wiki has no pages yet."
            return text, ToolInvocationResult(
                tool_ref=TEAM_WIKI_TOOL_REF,
                blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=text),),
            )

        @tool("wiki_read_page", response_format="content_and_artifact")
        async def wiki_read_page(slug: str) -> tuple[str, ToolInvocationResult]:
            """Read one wiki page's full text, by the slug the index gives you.

            Use this before relying on anything the wiki says — the index in
            your instructions carries titles only, and a title is not evidence.
            You get the whole page unless the text ends with an explicit cut
            marker; no marker means nothing was withheld, so do not call this
            again hoping for more. When the answer comes from a page, name that
            page so the user can check it.

            This tool READS. There is no tool here that writes to the wiki, so
            re-reading a page will never let you change it.
            """

            port = _require_port()
            started = time.monotonic()
            try:
                page = await port.read_page(slug, max_chars=PAGE_READ_MAX_CHARS)
            except Exception as exc:
                return _wiki_tool_failure(
                    action=f"read the wiki page '{slug}'",
                    exc=exc,
                    elapsed_s=time.monotonic() - started,
                )
            body = page.content_md.strip() or "(this page is empty)"
            text = f"# {page.title}\n\n{body}"
            if page.truncated:
                text += (
                    f"\n\n…[cut at {PAGE_READ_MAX_CHARS} characters — this page "
                    "is longer than what you were given]"
                )
            if page.slug in already_read or slug in already_read:
                text += _REREAD_NOTE
            already_read.update({slug, page.slug})
            return text, ToolInvocationResult(
                tool_ref=TEAM_WIKI_TOOL_REF,
                blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=text),),
            )

        return [wiki_list_pages, wiki_read_page]

    def middleware(
        self, ctx: CapabilityContext[EmptyModel, EmptyModel]
    ) -> Sequence[AgentMiddleware]:
        """ONLY the prompt fragment — the tools are not carried here.

        `tools()` and `middleware()` compose rather than replace each other:
        the assembler builds the tool carrier from `tools()` itself and calls
        this hook separately (`fred_runtime/capabilities/assembly.py`). Adding
        a carrier here would call `tools()` a second time and register both
        tools twice, so the model would see each of them twice in its schema.
        """

        return [_TeamWikiPromptMiddleware(ctx.services.team_wiki)]
