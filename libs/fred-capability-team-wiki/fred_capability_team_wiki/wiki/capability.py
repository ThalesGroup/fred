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
`TeamWikiCapability` (WIKI-03/04) — read and contribute to the team's wiki, spec
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
- **Writes are two steps and gated** (WIKI-04). `wiki_propose_*` stores a
  suggestion that changes nothing; `wiki_publish_proposal` is the call the
  platform's single approval gate pauses, because the gate runs BEFORE a tool
  and carries only a truncated argument preview — too little to diff a page
  against. There is no delete, rename or move tool, and the rules page is
  refused server-side whatever the configuration.
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
from fred_sdk.contracts.capability.hitl import HitlSpec
from fred_sdk.contracts.context import (
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
)
from fred_sdk.contracts.models import FieldSpec
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
from pydantic import BaseModel

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
    "changed, and reading it again will not change it. Answer the user with "
    "what you have, or propose a change if you have a tool for that.]"
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

    if status_code == 409:
        # A conflict is the one failure the model can fix by itself: someone
        # changed the page while the proposal waited. Without this branch it
        # read as "could not be reached" and the model retried unchanged.
        cause = (
            "the page changed while your proposal was waiting. Read it again "
            "and redo your edit on the new text"
        )
    elif status_code in (401, 403):
        # 403 is also how the server refuses the rules page, so the reason it
        # sent is kept below rather than replaced by a guess.
        cause = "that is not allowed"
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

    # The server's own message is kept whenever there is one: it names the
    # actual refusal ("the rules page cannot be changed by an agent") where the
    # status alone would have the model guess.
    detail = f" ({raw})" if raw and not timed_out else ""
    message = f"Could not {action}: {cause}{detail}."
    # `blocks` carries the same diagnostic as `content` (CAPAB-02): a Graph
    # agent's plain-dict invocation keeps only the artifact half.
    return message, ToolInvocationResult(
        tool_ref=TEAM_WIKI_TOOL_REF,
        is_error=True,
        blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=message),),
    )


def _page_path(pages: Sequence[WikiPageRef], page: WikiPageRef) -> str:
    """One page's address: its titles from the root, joined by " / "."""

    by_slug = {p.slug: p for p in pages}
    trail = [page.title]
    seen = {page.slug}
    parent = page.parent_slug
    # Bounded: a cycle left by a bad row must not hang a tool call.
    while parent and parent not in seen and len(trail) < 16:
        node = by_slug.get(parent)
        if node is None:
            break
        trail.append(node.title)
        seen.add(node.slug)
        parent = node.parent_slug
    return " / ".join(reversed(trail))


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


class _AmbiguousPath(Exception):
    """Several pages answer to the same short path."""

    def __init__(self, candidates: Sequence[str]) -> None:
        super().__init__("ambiguous path")
        self.candidates = list(candidates)


def resolve_path(pages: Sequence[WikiPageRef], path: str) -> WikiPageRef | None:
    """The page a model means by `path`, or None.

    Two ways in, because a model writes what it sees. A full path from the root
    ("Accueil / Thales Italie") is unique — sibling titles are refused by the
    control-plane, so no two pages share one. A bare title is accepted too,
    since that is what a model usually types, and is unique often enough to be
    worth resolving; when it is not, `_AmbiguousPath` carries the full paths so
    the model can pick rather than guess.

    Comparison folds case and collapses whitespace: the model is retyping a
    title it read, not copying an identifier.
    """

    wanted = _norm(path.replace("/", " / "))
    if not wanted:
        return None
    full = [p for p in pages if _norm(_page_path(pages, p)) == wanted]
    if len(full) == 1:
        return full[0]

    leaf = _norm(path.rsplit("/", 1)[-1])
    by_title = [p for p in pages if _norm(p.title) == leaf]
    if len(by_title) == 1:
        return by_title[0]
    if len(by_title) > 1:
        raise _AmbiguousPath([_page_path(pages, p) for p in by_title])
    return None


def _format_index(pages: Sequence[WikiPageRef]) -> str:
    """The page list as an indented tree of titles.

    Titles only, deliberately: a page's slug is an opaque id, and a model that
    can see one will sooner or later print it to the user, who has no use for
    `6adb844e`. Asking it not to does not work — anything in the context can
    come back out — so the identifier stays out of the context entirely and
    pages are addressed by their path (`resolve_path`).
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
        line = f"{'  ' * depth}- {page.title}"
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

    def __init__(self, port: TeamWikiPort | None, *, can_write: bool) -> None:
        super().__init__()
        self._port = port
        self._can_write = can_write
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
            "Address a page by its path in the index below — its titles from "
            'the top joined by " / ", as the indentation shows them — and '
            "pass that to wiki_read_page. Read a page before relying on it: a "
            "title is not evidence of what a page says. Pages have no other "
            "name than their title, so never quote an identifier to the user."
        )
        # Field evidence, 2026-09-07: asked to add a fact to a page, an agent
        # read it, found no way to write, and answered "Mise à jour appliquée"
        # with the new Markdown — a change the user believed had been saved and
        # that never existed. A capability that only reads has to say so, or a
        # model told it "has access to the wiki" will assume the rest.
        if self._can_write:
            parts.append(
                "\nYou can read this wiki and propose changes to it. A proposal "
                "changes nothing on its own: prepare it with wiki_propose_edit "
                "or wiki_propose_page, then call wiki_publish_proposal, which "
                "asks the user to approve it. Read a page before proposing an "
                "edit — your text replaces it whole, so it must be the complete "
                "page as it should end up. Say a page was written only after a "
                "publish call has come back successful."
                "\nContent is the ONLY thing you can change. You cannot move, "
                "rename or delete a page, and editing its text will not move "
                "it — if the user asks for any of those, say plainly that you "
                "cannot and that an editor does it from the Wiki screen. You "
                "can never change the rules page."
                "\nA new page can only sit under a page that already exists, "
                "so to build a parent and its children, publish the parent "
                "first and propose the children after — naming a parent you "
                "have not published yet will not find it."
            )
        else:
            parts.append(
                "\nYou can READ this wiki. You cannot change it: there is no "
                "tool here that creates, edits or deletes a page, and nothing "
                "you write in your answer reaches it. If the user asks you to "
                "add or correct something, give them the text you would put "
                "there and tell them an editor has to paste it into the page "
                "from the Wiki screen. Never say a page has been updated, "
                "created or saved — it has not."
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


class TeamWikiConfig(BaseModel):
    """Agent-creation / stored config of the `team_wiki` capability.

    One knob (RFC §7.2): whether this agent may only read the wiki, or may
    also propose changes to it. Read is the default — an agent that can write
    is a deliberate choice, not what you get by ticking a box.
    """

    mode: str = "read"


class TeamWikiCapability(AgentCapability[TeamWikiConfig, TeamWikiConfig, EmptyModel]):
    """Read access to the calling team's wiki, through
    `RuntimeServices.team_wiki` (see the module docstring for the doctrine)."""

    manifest = CapabilityManifest(
        id="team_wiki",
        version="0.1.0",
        name="capability.team_wiki.name",
        description="capability.team_wiki.description",
        icon="book_2",
        kind="tool",
        # One field only (RFC §7.2). There is deliberately no scoping knob:
        # what an agent may reach is the whole team wiki, and a per-agent scope
        # would be a second, weaker access rule beside the team's own.
        config_fields=[
            FieldSpec(
                key="mode",
                type="string",
                title="capability.team_wiki.fields.mode.title",
                description="capability.team_wiki.fields.mode.description",
                default="read",
                enum=["read", "read_write"],
            ),
        ],
        # ReAct only — see the module docstring. The default would let a Graph
        # agent select this capability and answer without the team's rules.
        execution_models=("react",),
        # team_scope stays the ADMIN_GATED default: enabling this capability is
        # what makes a team's wiki exist at all, for its agents and its people.
    )
    ConfigModel = TeamWikiConfig

    def hitl_specs(self) -> Sequence[HitlSpec]:
        """Publishing is the one act a human must sign off on.

        Not `wiki_propose_*`: a proposal changes nothing and gating it would
        ask the user to approve a draft they cannot see yet. The gate pauses a
        tool BEFORE it runs and carries only a truncated argument preview — too
        little to diff a page — so the proposal is stored first and its id is
        what the approval prompt carries. The modal fetches it and shows the
        diff. See `docs/swift/rfc/TEAM-WIKI-RFC.md` §11.
        """

        return [HitlSpec(tool="wiki_publish_proposal", require=True)]

    def tools(
        self, ctx: CapabilityContext[TeamWikiConfig, EmptyModel]
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
        # What each prepared proposal would do, so publishing can say what it
        # actually changed instead of only that it succeeded.
        proposal_kind: dict[str, str] = {}
        # The tree, fetched at most once per turn and shared by every tool that
        # has to turn a path into a page. Dropped after a publish, which is the
        # only thing here that can add or rename one.
        tree: list[WikiPageRef] | None = None
        tree_lock = asyncio.Lock()

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

        async def _tree() -> list[WikiPageRef]:
            nonlocal tree
            async with tree_lock:
                if tree is None:
                    tree = list(await _require_port().list_pages())
                return tree

        def _resolution_failure(message: str) -> tuple[str, ToolInvocationResult]:
            return message, ToolInvocationResult(
                tool_ref=TEAM_WIKI_TOOL_REF,
                is_error=True,
                blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=message),),
            )

        async def _resolve(
            path: str, *, action: str
        ) -> WikiPageRef | tuple[str, ToolInvocationResult]:
            """The page at `path`, or the result to hand back instead.

            Returning the failure rather than raising keeps all three shapes —
            the wiki being unreachable, no such page, several pages to pick
            from — as ordinary tool output the model can act on.
            """

            started = time.monotonic()
            try:
                pages = await _tree()
            except Exception as exc:
                # Resolution needs the tree, so a wiki that cannot be reached
                # fails here rather than at the call the model asked for.
                return _wiki_tool_failure(
                    action=action, exc=exc, elapsed_s=time.monotonic() - started
                )
            try:
                page = resolve_path(pages, path)
            except _AmbiguousPath as ambiguous:
                listed = "; ".join(ambiguous.candidates)
                return _resolution_failure(
                    f"Several wiki pages are called '{path}': {listed}. Call "
                    "again with the full path of the one you mean."
                )
            if page is None:
                return _resolution_failure(
                    f"There is no wiki page at '{path}'. Address a page by its "
                    "path in the index in your instructions, parent first, "
                    "like 'Parent page / Child page'."
                )
            return page

        @tool("wiki_list_pages", response_format="content_and_artifact")
        async def wiki_list_pages() -> tuple[str, ToolInvocationResult]:
            """List every page in the team's wiki, as an indented tree.

            Indentation is the hierarchy. A page's address is its titles from
            the top joined by " / " — "Parent page / Child page" — and that is
            what wiki_read_page takes. The same index is already in your
            instructions: call this only to refresh it after a change, or when
            the instructions say pages were omitted.
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
        async def wiki_read_page(path: str) -> tuple[str, ToolInvocationResult]:
            """Read one wiki page's full text, by its path in the index.

            A path is the page's titles from the top, joined by " / ", as the
            index's indentation shows them: "Parent page / Child page". The
            page's own title alone works too when only one page has it.

            Use this before relying on anything the wiki says — a title in the
            index is not evidence of what the page contains.
            You get the whole page unless the text ends with an explicit cut
            marker; no marker means nothing was withheld, so do not call this
            again hoping for more. When the answer comes from a page, name that
            page so the user can check it.

            This tool READS. There is no tool here that writes to the wiki, so
            re-reading a page will never let you change it.
            """

            port = _require_port()
            found = await _resolve(path, action=f"read the wiki page '{path}'")
            if not isinstance(found, WikiPageRef):
                return found
            slug = found.slug
            started = time.monotonic()
            try:
                page = await port.read_page(slug, max_chars=PAGE_READ_MAX_CHARS)
            except Exception as exc:
                return _wiki_tool_failure(
                    action=f"read the wiki page '{path}'",
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

        if ctx.config.mode != "read_write":
            return [wiki_list_pages, wiki_read_page]

        # --- the write half ------------------------------------------------
        #
        # Two tools, two steps: proposing stores a suggestion that changes
        # nothing; publishing is the call the platform's approval gate pauses.
        # No delete, rename or move tool exists — that is the enforcement of
        # the RFC's §5.4 invariant, an absence rather than a check.

        _PREPARED = (
            "Nothing is written yet — call wiki_publish_proposal with this id "
            "to ask the user to approve it."
        )

        @tool("wiki_propose_edit", response_format="content_and_artifact")
        async def wiki_propose_edit(
            path: str, content_md: str
        ) -> tuple[str, ToolInvocationResult]:
            """Suggest new content for an existing wiki page, by its path.

            A path is the page's titles from the top joined by " / ", the same
            address wiki_read_page takes.

            Read the page first: `content_md` REPLACES it whole, so it must be
            the complete page as you want it to end up, not just your addition.
            Keep what was already there unless the user asked to remove it.

            This stores a suggestion and changes nothing in the wiki.
            """

            port = _require_port()
            found = await _resolve(path, action=f"propose an edit to '{path}'")
            if not isinstance(found, WikiPageRef):
                return found
            started = time.monotonic()
            try:
                proposal = await port.propose_edit(
                    slug=found.slug, content_md=content_md
                )
            except Exception as exc:
                return _wiki_tool_failure(
                    action=f"propose an edit to '{path}'",
                    exc=exc,
                    elapsed_s=time.monotonic() - started,
                )
            proposal_kind[proposal.proposal_id] = "edit"
            text = f"Proposal {proposal.proposal_id} prepared ({proposal.summary}). {_PREPARED}"
            return text, ToolInvocationResult(
                tool_ref=TEAM_WIKI_TOOL_REF,
                blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=text),),
            )

        @tool("wiki_propose_page", response_format="content_and_artifact")
        async def wiki_propose_page(
            title: str, content_md: str, parent_path: str | None = None
        ) -> tuple[str, ToolInvocationResult]:
            """Suggest a NEW wiki page. Use wiki_propose_edit for one that exists.

            `parent_path` nests it under an existing page, addressed the way
            wiki_read_page addresses one; omit it for a top-level page. Check
            the index first — a second page on a topic the wiki already covers
            is worse than a longer one. Two pages under the same parent cannot
            share a title, so pick one that is not already in that branch.

            This stores a suggestion and changes nothing in the wiki.
            """

            port = _require_port()
            parent_slug: str | None = None
            if parent_path:
                found = await _resolve(
                    parent_path, action=f"propose the page '{title}'"
                )
                if not isinstance(found, WikiPageRef):
                    return found
                parent_slug = found.slug
            started = time.monotonic()
            try:
                proposal = await port.propose_page(
                    title=title, content_md=content_md, parent_slug=parent_slug
                )
            except Exception as exc:
                return _wiki_tool_failure(
                    action=f"propose the page '{title}'",
                    exc=exc,
                    elapsed_s=time.monotonic() - started,
                )
            proposal_kind[proposal.proposal_id] = "page"
            text = f"Proposal {proposal.proposal_id} prepared ({proposal.summary}). {_PREPARED}"
            return text, ToolInvocationResult(
                tool_ref=TEAM_WIKI_TOOL_REF,
                blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=text),),
            )

        @tool("wiki_publish_proposal", response_format="content_and_artifact")
        async def wiki_publish_proposal(
            proposal_id: str,
        ) -> tuple[str, ToolInvocationResult]:
            """Submit a prepared proposal for the user's approval.

            The user is shown what would change and decides. Call it only with
            an id a propose tool just gave you, and only once — if the user
            declines, do not call it again with the same id.
            """

            nonlocal tree
            port = _require_port()
            started = time.monotonic()
            try:
                slug = await port.publish_proposal(proposal_id)
            except Exception as exc:
                return _wiki_tool_failure(
                    action="publish the proposal",
                    exc=exc,
                    elapsed_s=time.monotonic() - started,
                )
            # The tree just changed, and the cached copy would still be
            # missing a page the model may go on to read this turn.
            async with tree_lock:
                tree = None
            published = next((p for p in await _tree() if p.slug == slug), None)
            where = f" '{_page_path(await _tree(), published)}'" if published else ""
            # Named for what it did, not just that it worked. An agent that
            # tried to MOVE a page through an edit read a bare "Published" as
            # confirmation of the move, and told the user so.
            did = (
                "Its text was replaced; where it sits in the tree is unchanged"
                if proposal_kind.get(proposal_id) == "edit"
                else "It was created"
            )
            text = (
                f"Published. The page{where} is live. {did}. It carries the "
                "review mark every agent-written page gets until an editor "
                "clears it."
            )
            return text, ToolInvocationResult(
                tool_ref=TEAM_WIKI_TOOL_REF,
                blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=text),),
            )

        return [
            wiki_list_pages,
            wiki_read_page,
            wiki_propose_edit,
            wiki_propose_page,
            wiki_publish_proposal,
        ]

    def middleware(
        self, ctx: CapabilityContext[TeamWikiConfig, EmptyModel]
    ) -> Sequence[AgentMiddleware]:
        """ONLY the prompt fragment — the tools are not carried here.

        `tools()` and `middleware()` compose rather than replace each other:
        the assembler builds the tool carrier from `tools()` itself and calls
        this hook separately (`fred_runtime/capabilities/assembly.py`). Adding
        a carrier here would call `tools()` a second time and register both
        tools twice, so the model would see each of them twice in its schema.
        """

        return [
            _TeamWikiPromptMiddleware(
                ctx.services.team_wiki, can_write=ctx.config.mode == "read_write"
            )
        ]
