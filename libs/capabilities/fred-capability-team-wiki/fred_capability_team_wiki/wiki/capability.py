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
- **Writes are drafts the person confirms** (WIKI-04). `wiki_propose_*` stores
  a draft bound to the conversation that changes nothing; `wiki_submit_proposal`
  is the call the platform's approval gate pauses. The person's approval card
  confirms (or declines) the draft with their own token; editors then accept or
  refuse it, and an editor's confirmation accepts it. The agent can never
  submit or publish: after the gate the tool only reads the status back. There
  is no delete, rename or move tool, and the rules page is refused server-side
  whatever the configuration.
- **A whole-page replacement requires a whole-page read.** A page can hold up
  to 100 000 chars and `wiki_read_page` returns `PAGE_READ_MAX_CHARS` at a
  time, so `tools()` tracks contiguous, revision-consistent coverage per slug
  and `wiki_propose_page_text` — which REPLACES a page whole — refuses until
  a slug has been read start to end this turn (RUNTIME-EXECUTION-CONTRACT.md
  §8.75).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

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
    ToolFailure,
    ToolFailureCode,
    ToolInvocationResult,
)
from fred_sdk.contracts.models import FieldSpec
from fred_sdk.contracts.runtime import (
    WIKI_RULES_MAX_CHARS,
    TeamWikiPort,
    WikiFileUnreadableError,
    WikiPageContent,
    WikiPageRef,
    unwrap_run_stop_error,
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

# How much of one page a single wiki_read_page call returns. A wiki page is a
# synthesis, and the control-plane caps it at 100 000 characters — far more
# than one call should hand the model at once, so a read returns it in bounded
# segments (offset-based continuation, same shape as DocumentMarkdownPort)
# rather than a single silent cut.
PAGE_READ_MAX_CHARS = 8_000

# The index injected into the prompt. Titles only: the point is that the model
# knows what the team has written down and can ask for it by slug, not that it
# reads the wiki every turn.
INDEX_MAX_CHARS = 4_000

# One call to wiki_list_pages. Independent of INDEX_MAX_CHARS on purpose: the
# injected index repeats on every model call this turn, so its budget favors
# staying small; this tool is called on demand, once per page of results, so
# it can afford more — and unlike the index it must be a COMPLETE discovery
# mechanism on its own (WIKI-05: the index used to point an omitted-pages
# model here for "the rest", and this tool returned the identical truncated
# prefix — the omitted pages were unreachable by any tool).
LIST_PAGES_MAX_CHARS = 8_000

# Appended when the same page is read twice in one turn. The content is still
# returned — a trimmed history can legitimately cost the model a page it read —
# but the loop this breaks is real: a model asked to edit a page, with no tool
# that can, re-read it six times before answering that it could not retrieve it.
_REREAD_NOTE = (
    "\n\n[You already read this page earlier in this turn and it has not "
    "changed, and reading it again will not change it. Answer the user with "
    "what you have, or propose a change if you have a tool for that.]"
)


def _ok(text: str) -> tuple[str, ToolInvocationResult]:
    """A successful tool result: the text, carried in both halves (CAPAB-02)."""

    return text, ToolInvocationResult(
        tool_ref=TEAM_WIKI_TOOL_REF,
        blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=text),),
    )


def _segment_note(tool_name: str, path: str, window: WikiPageContent) -> str:
    """Where a bounded read stopped, and how to continue it."""

    if window.next_offset is None:
        return f"\n\n[End reached ({window.total_chars} chars total).]"
    return (
        f"\n\n[Read chars {window.offset}-"
        f"{window.offset + len(window.content_md)} of {window.total_chars}. "
        "MORE TEXT REMAINS — you have NOT seen all of it yet. Call "
        f"{tool_name}('{path}', offset={window.next_offset}) to keep reading "
        "before relying on or replacing its content.]"
    )


# What wiki_submit_proposal reports for a proposal the user's decision left
# unpublished, read back from the Control Plane after the approval gate.
_SUBMIT_OUTCOMES = {
    "pending": "Submitted: the user confirmed it, and it now waits for an editor "
    "of the space to accept or refuse it. It is not in the wiki yet.",
    "draft": "The user has not confirmed this proposal. Nothing was submitted "
    "and nothing is in the wiki.",
    "closed": "This proposal is no longer pending: it was declined, refused or "
    "withdrawn. Nothing was written.",
}


def _wiki_tool_failure(
    *, action: str, exc: Exception, elapsed_s: float
) -> tuple[str, ToolInvocationResult]:
    """Turn a wiki tool-call failure into an actionable message plus an
    ``failure`` artifact.

    The runtime surfaces `ToolInvocationResult.failure` directly, so a failing
    tool returns such a result instead of raising. Failure shape arrives via
    the SDK-typed `TeamWikiPortError` attributes read with `getattr` — this
    module never imports the adapter's HTTP stack. A run stop anywhere in the
    failure's chain is raised instead: it ends the run, never the tool call.
    """

    run_stop = unwrap_run_stop_error(exc)
    if run_stop is not None:
        raise run_stop from None

    status_code = getattr(exc, "status_code", None)
    timed_out = bool(getattr(exc, "timed_out", False))
    raw = str(exc).strip()

    if isinstance(exc, WikiFileUnreadableError):
        cause = "an agent can read only md, csv, txt and json text files"
    elif status_code == 409:
        # A conflict is the one failure the model can fix by itself: the entry
        # changed since it was read (revision_changed, a stale base) or the
        # name is taken. Without this branch it read as "could not be reached"
        # and the model retried unchanged.
        cause = (
            "it conflicts with the wiki as it is now (the entry changed since "
            "you read it, or its name is taken). Read it again and redo your change"
        )
    elif status_code in (401, 403):
        # 403 is also how the server refuses the rules page, so the reason it
        # sent is kept below rather than replaced by a guess.
        cause = "that is not allowed"
    elif status_code == 404:
        cause = "it was not found"
    elif timed_out:
        cause = "the wiki did not answer in time"
    elif status_code is not None and status_code < 500:
        # Invalid name or extension, quota, size, transfer capacity: the
        # server's reason below says which.
        cause = "the wiki refused it"
    else:
        cause = "the wiki could not be reached"

    logger.warning(
        "Team wiki tool failure (%s, %.1fs) — status=%s timed_out=%s; "
        "degraded to a failure artifact.",
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
        failure=ToolFailure.from_http_status(status_code, timed_out=timed_out),
        blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=message),),
    )


def _page_path(
    pages: Sequence[WikiPageRef],
    page: WikiPageRef,
    by_slug: dict[str, WikiPageRef] | None = None,
) -> str:
    """One page's address: its titles from the root, joined by " / ".

    `by_slug` is built once by a caller that walks every page — rebuilding it
    per page made resolving a path quadratic, on the event loop, between a
    tool call and the next model request.
    """

    by_slug = by_slug if by_slug is not None else {p.slug: p for p in pages}
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


def _path_key(text: str) -> str:
    """Both sides of a path comparison, folded the same way.

    The separator is normalised on the STORED path too, not only on what the
    model typed: a page titled "Q1/Q2" would otherwise fold to `q1/q2` on one
    side and `q1 / q2` on the other, and be unaddressable by any tool.
    """

    return _norm(text.replace("/", " / "))


def resolve_path(pages: Sequence[WikiPageRef], path: str) -> WikiPageRef | None:
    """The page a model means by `path`, or None.

    Two ways in, because a model writes what it sees. A full path from the root
    ("Accueil / Thales Italie") is unique — sibling titles are refused by the
    control-plane, so no two pages share one. A BARE title is accepted as well,
    since that is what a model usually types; when several pages carry it,
    `_AmbiguousPath` lists the full paths so the model can pick rather than
    guess.

    The bare-title fallback applies ONLY to an input with no separator. A path
    that names a parent is a claim about where the page sits, and falling back
    to its last segment answered "Archive / Onboarding" with "HR / Onboarding"
    — a different page, whose whole text a write would then have replaced.

    Comparison folds case and collapses whitespace: the model is retyping a
    title it read, not copying an identifier.
    """

    wanted = _path_key(path)
    if not wanted:
        return None
    by_slug = {p.slug: p for p in pages}
    full = [p for p in pages if _path_key(_page_path(pages, p, by_slug)) == wanted]
    if len(full) == 1:
        return full[0]
    if len(full) > 1:
        # Sibling titles are unique, so two identical full paths mean a title
        # containing a separator has collided with a real branch. Refusing is
        # the only honest answer; picking one hides a page for good.
        raise _AmbiguousPath([_page_path(pages, p, by_slug) for p in full])

    if "/" in path:
        return None
    by_title = [p for p in pages if _norm(p.title) == wanted]
    if len(by_title) == 1:
        return by_title[0]
    if len(by_title) > 1:
        raise _AmbiguousPath([_page_path(pages, p, by_slug) for p in by_title])
    return None


# How a listing marks a file entry, so the model reads it with wiki_read_file.
_FILE_MARK = " (file)"


def _format_index(pages: Sequence[WikiPageRef]) -> str:
    """The page list as an indented tree of titles — a compact PREVIEW, not a
    complete discovery mechanism. `wiki_list_pages` (`_format_page_batch`) is
    that: paginated, so it can promise completeness this cannot.

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
        line = (
            f"{'  ' * depth}- {page.title}{_FILE_MARK if page.kind == 'file' else ''}"
        )
        if used + len(line) + 1 > INDEX_MAX_CHARS:
            omitted = len(pages) - len(lines)
            break
        used += len(line) + 1
        lines.append(line)
    if omitted:
        lines.append(
            f"  …[{omitted} more pages not shown here — call wiki_list_pages to "
            "browse the complete, addressable list page by page]"
        )
    return "\n".join(lines)


def _format_page_batch(
    pages: Sequence[WikiPageRef], *, offset: int
) -> tuple[str, int | None]:
    """One bounded, self-contained slice of the full page list, starting at
    `offset`. Each line is a page's FULL PATH, not an indented title: unlike
    `_format_index`, a slice does not start at the root, so a page's
    ancestors are not necessarily in the same slice to lean on for context —
    the path carries that on every line regardless of where a boundary falls.

    Returns the slice's text and the offset to pass next, or None once the
    slice reaches the end of the list. Always includes at least one page when
    `offset` still has pages left, even one whose own path alone exceeds the
    budget, so a pathologically long title cannot stall pagination forever.
    """

    by_slug = {p.slug: p for p in pages}
    lines: list[str] = []
    used = 0
    index = offset
    for page in pages[offset:]:
        mark = _FILE_MARK if page.kind == "file" else ""
        line = f"- {_page_path(pages, page, by_slug)}{mark}"
        if lines and used + len(line) + 1 > LIST_PAGES_MAX_CHARS:
            break
        used += len(line) + 1
        lines.append(line)
        index += 1
    next_offset = index if index < len(pages) else None
    return "\n".join(lines), next_offset


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
        rules_read = asyncio.ensure_future(port.read_rules())
        pages_read = asyncio.ensure_future(port.list_pages())
        try:
            rules, pages = await asyncio.gather(rules_read, pages_read)
        except Exception as exc:
            run_stop = unwrap_run_stop_error(exc)
            if run_stop is not None:
                # The run ends here, so its other read must not outlive it.
                for read in (rules_read, pages_read):
                    read.cancel()
                await asyncio.gather(rules_read, pages_read, return_exceptions=True)
                raise run_stop from None
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
            "pass that to wiki_read_page. Entries marked (file) are files: "
            "read one with wiki_read_file (md, csv, txt and json only; other "
            "formats cannot be read). Read an entry before relying on it: a "
            "title is not evidence of what it says. Entries have no other "
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
                "is a draft that changes nothing: prepare it with "
                "wiki_propose_page_text, wiki_propose_page or wiki_propose_file "
                "(one of this conversation's files, by its document_id), then "
                "call wiki_submit_proposal, which asks the user to confirm it. "
                "Once confirmed, an editor of the space accepts or refuses it; "
                "an editor's own confirmation accepts it at once. Read a page "
                "before proposing an edit — your text replaces it whole, so it "
                "must be the complete page as it should end up. A long page "
                "comes back in more than one wiki_read_page call; keep reading "
                "to the end before proposing, or the tool will refuse. Say "
                "something is in the wiki only after wiki_submit_proposal "
                "reports it published."
                "\nContent is the ONLY thing you can change. You cannot move, "
                "rename or delete a page, and editing its text will not move "
                "it — if the user asks for any of those, say plainly that you "
                "cannot and that an editor does it from the Wiki screen. You "
                "can never change the rules page."
                "\nA new page or file can only sit under a page that already "
                "exists, so to build a parent and its children, have the parent "
                "published first and propose the children after — naming a "
                "parent that is not published yet will not find it."
            )
        else:
            parts.append(
                "\nYou can READ this wiki. You cannot change it: there is no "
                "tool here that creates, edits or deletes an entry, and nothing "
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


@dataclass(slots=True)
class _SlugReadState:
    """One slug's read progress this turn — kept as one object, not three
    parallel dicts, because a revision change invalidates `revision`,
    `covered_to` and `complete` together; splitting them risks an update to
    one without the other two (see `wiki_read_page`/`wiki_propose_page_text`).
    """

    revision: str | None = None
    covered_to: int = 0
    complete: bool = False


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
        """Submitting is the one act the person must confirm.

        Not `wiki_propose_*`: a draft changes nothing and gating it would ask
        the user to approve something they cannot see yet. The gate pauses a
        tool BEFORE it runs and carries only a truncated argument preview — too
        little to diff a page — so the draft is stored first and its id is what
        the approval prompt carries. The card fetches it, shows it, and submits
        or deletes it with the person's own token.
        """

        return [HitlSpec(tool="wiki_submit_proposal", require=True)]

    def tools(
        self, ctx: CapabilityContext[TeamWikiConfig, EmptyModel]
    ) -> Sequence[BaseTool]:
        """The two read tools, bound to the turn's typed context.

        Hard split: the signatures carry ONLY LLM arguments — a slug. The port
        comes from this closure, and with it the team and the caller's identity
        the agent can neither see nor choose.
        """

        services = ctx.services
        # (slug, offset) segments already read this turn — see `_REREAD_NOTE`:
        # a model with no way to act on a page it has read will otherwise call
        # this again, and again, in the field.
        already_read: set[tuple[str, int]] = set()
        # Per-slug read progress this turn: which revision, how far a
        # contiguous chain of reads has covered from offset 0 (a continuation
        # quoting an offset beyond this would skip unseen text), and whether
        # it was read start-to-finish at one consistent revision — the only
        # grounds wiki_propose_page_text accepts for replacing a page whole.
        # One dict of one small object per slug, not three parallel ones: a
        # revision change invalidates all three together, and the 409 handler
        # below only has to drop one entry, not remember to clear three.
        read_state: dict[str, _SlugReadState] = {}
        # Guards `read_state` above: a ReAct round can dispatch several tool
        # calls from one model turn concurrently (LangGraph gathers them), so
        # two reads of the same slug could otherwise interleave their updates
        # and leave this bookkeeping inconsistent.
        read_state_lock = asyncio.Lock()
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

        def _resolution_failure(
            message: str, code: ToolFailureCode = ToolFailureCode.invalid_arguments
        ) -> tuple[str, ToolInvocationResult]:
            # Every refusal here asks the model to correct its call, except a
            # path that names no page.
            return message, ToolInvocationResult(
                tool_ref=TEAM_WIKI_TOOL_REF,
                failure=ToolFailure(code=code),
                blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=message),),
            )

        async def _resolve(
            path: str, *, action: str, kind: str = "page"
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
                    "like 'Parent page / Child page'.",
                    ToolFailureCode.resource_unavailable,
                )
            if page.kind != kind:
                tool_name = (
                    "wiki_read_file" if page.kind == "file" else "wiki_read_page"
                )
                return _resolution_failure(
                    f"'{path}' is a {page.kind}, not a {kind}: use {tool_name} "
                    "to read it. Only a page can hold other entries."
                )
            return page

        @tool("wiki_list_pages", response_format="content_and_artifact")
        async def wiki_list_pages(offset: int = 0) -> tuple[str, ToolInvocationResult]:
            """List every page in the team's wiki, exhaustively and page by page.

            Each line is one page's full path — its titles from the top
            joined by " / ", e.g. "Parent page / Child page" — the same
            address wiki_read_page takes. Call with no argument for the
            first page of results, to see the complete list from the start
            or to refresh it after a change. Each call returns ONE page and
            a `total` count; when it ends with "... N more — call again
            with offset=N to continue", call again with that offset. NEVER
            tell the user you have listed every page after one call without
            checking for that line — the index already in your
            instructions is a compact preview, and this tool's own output
            can also span more than one call.
            """

            nonlocal tree
            # Before the try: a missing port is a wiring fault and must stay
            # loud, not degrade into "the wiki could not be reached".
            _require_port()
            effective_offset = max(offset, 0)
            started = time.monotonic()
            try:
                # Always refreshed, continuation calls included: reusing the
                # cache across a pagination sequence would misalign a later
                # offset against a list a same-turn wiki_submit_proposal
                # already reordered underneath it (its own refresh runs
                # regardless of what this tool does).
                async with tree_lock:
                    tree = None
                pages = await _tree()
            except Exception as exc:
                return _wiki_tool_failure(
                    action="list the wiki pages",
                    exc=exc,
                    elapsed_s=time.monotonic() - started,
                )
            if not pages:
                return _ok("This wiki has no pages yet.")
            if effective_offset >= len(pages):
                return _ok(
                    f"total={len(pages)}. There are no more pages after the "
                    "ones you already listed."
                )
            body, next_offset = _format_page_batch(pages, offset=effective_offset)
            lines = [f"total={len(pages)} offset={effective_offset}", body]
            if next_offset is not None:
                lines.append(
                    f"... {len(pages) - next_offset} more — call again with "
                    f"offset={next_offset} to continue."
                )
            return _ok("\n".join(lines))

        @tool("wiki_read_page", response_format="content_and_artifact")
        async def wiki_read_page(
            path: str, offset: int = 0
        ) -> tuple[str, ToolInvocationResult]:
            """Read one wiki page's text, one bounded segment at a time, by its
            path in the index.

            A path is the page's titles from the top, joined by " / ", as the
            index's indentation shows them: "Parent page / Child page". The
            page's own title alone works too when only one page has it.

            Use this before relying on anything the wiki says — a title in the
            index is not evidence of what the page contains.

            Leave `offset` unset to read from the start. A page longer than
            one segment says so and gives you the `offset` to call again with;
            keep calling until it says you have reached the end before you
            conclude you have seen the whole page — a segment that does not
            reach the end is NOT the whole page, even if it looks complete.
            wiki_propose_page_text refuses to replace a page you have not read
            all the way to the end this turn, so do not skip ahead. When the
            answer comes from a page, name that page so the user can check it.

            This tool READS. There is no tool here that writes to the wiki, so
            re-reading a page will never let you change it.
            """

            port = _require_port()
            found = await _resolve(path, action=f"read the wiki page '{path}'")
            if not isinstance(found, WikiPageRef):
                return found
            slug = found.slug
            offset = max(offset, 0)
            async with read_state_lock:
                state = read_state.get(slug)
                expected_offset = state.covered_to if state is not None else 0
                if offset != 0 and offset > expected_offset:
                    return _resolution_failure(
                        f"'{path}' was not read up to offset {offset} this turn. "
                        f"Call wiki_read_page('{path}') to read it from the "
                        f"start, or wiki_read_page('{path}', "
                        f"offset={expected_offset}) to continue where your "
                        "last read of it left off."
                    )
                started = time.monotonic()
                try:
                    page = await port.read_page(
                        slug, max_chars=PAGE_READ_MAX_CHARS, offset=offset
                    )
                except Exception as exc:
                    return _wiki_tool_failure(
                        action=f"read the wiki page '{path}'",
                        exc=exc,
                        elapsed_s=time.monotonic() - started,
                    )
                prior_revision = state.revision if state is not None else None
                revision_changed = (
                    prior_revision is not None and page.revision_id != prior_revision
                )
                if offset > 0 and revision_changed:
                    # A port that does not pin content for the turn could hand
                    # back a later revision mid-read; discard rather than
                    # splice two revisions together (offset=0 restarts fresh).
                    read_state.pop(slug, None)
                    return _resolution_failure(
                        f"'{path}' changed while you were reading it, so "
                        f"continuing from offset {offset} would mix two "
                        "different versions of the page into one. Start "
                        f"again with wiki_read_page('{path}')."
                    )
                if revision_changed:
                    # offset == 0 here: a fresh start landed on a different
                    # revision than the one this slug's state was tracked
                    # against. That progress belongs to a page that no longer
                    # exists server-side — coverage for THIS read starts at
                    # zero, never inherited via max() below.
                    expected_offset = 0
                body = page.content_md.strip() or (
                    "(this page is empty)" if offset == 0 else "(no more text)"
                )
                text = f"# {page.title}\n\n{body}" if offset == 0 else body
                read_key = (slug, offset)
                if read_key in already_read or (page.slug, offset) in already_read:
                    text += _REREAD_NOTE
                already_read.update({read_key, (page.slug, offset)})
                state = read_state.setdefault(slug, _SlugReadState())
                read_state[page.slug] = state
                if page.revision_id is not None:
                    state.revision = page.revision_id
                state.complete = page.next_offset is None
                state.covered_to = max(
                    expected_offset, page.next_offset or page.total_chars
                )
                text += _segment_note("wiki_read_page", path, page)
            return _ok(text)

        @tool("wiki_read_file", response_format="content_and_artifact")
        async def wiki_read_file(
            path: str, offset: int = 0
        ) -> tuple[str, ToolInvocationResult]:
            """Read one wiki FILE's text, one bounded segment at a time, by its
            path in the index (entries marked "(file)").

            Only md, csv, txt and json files can be read; any other format is
            reported unreadable. Leave `offset` unset to read from the start;
            keep calling with the `offset` it gives you until it says you have
            reached the end. When the answer comes from a file, name it.
            """

            port = _require_port()
            action = f"read the wiki file '{path}'"
            found = await _resolve(path, action=action, kind="file")
            if not isinstance(found, WikiPageRef):
                return found
            started = time.monotonic()
            try:
                window = await port.read_file(
                    found.slug, max_chars=PAGE_READ_MAX_CHARS, offset=max(offset, 0)
                )
            except Exception as exc:
                return _wiki_tool_failure(
                    action=action, exc=exc, elapsed_s=time.monotonic() - started
                )
            head = f"# {window.title}\n\n" if window.offset == 0 else ""
            body = window.content_md or "(no more text)"
            return _ok(f"{head}{body}{_segment_note('wiki_read_file', path, window)}")

        if ctx.config.mode != "read_write":
            return [wiki_list_pages, wiki_read_page, wiki_read_file]

        # --- the write half ------------------------------------------------
        #
        # Proposing stores a draft that changes nothing; submitting is the call
        # the platform's approval gate pauses, and the person's card confirms
        # it. No delete, rename or move tool exists — that is the enforcement
        # of the RFC's §5.4 invariant, an absence rather than a check.

        _PREPARED = (
            "Nothing is written yet — call wiki_submit_proposal with this id "
            "to ask the user to confirm it."
        )

        # Named for its scope, not for "editing": a model asked to reorganise
        # the wiki reads `wiki_propose_edit` as covering that, and in the field
        # one used it to "move" two pages by republishing their own text.
        @tool("wiki_propose_page_text", response_format="content_and_artifact")
        async def wiki_propose_page_text(
            path: str, content_md: str
        ) -> tuple[str, ToolInvocationResult]:
            """Suggest new TEXT for an existing wiki page, by its path.

            This changes what the page says and nothing else. It cannot move,
            rename or delete a page — no tool here can.

            A path is the page's titles from the top joined by " / ", the same
            address wiki_read_page takes.

            Read the page with wiki_read_page THIS TURN first, all the way to
            its end — required, not just advice: `content_md` REPLACES it
            whole, so it must be the complete page as you want it to end up,
            not just your addition, and this is refused until wiki_read_page
            has told you that you reached the end. Keep what was already
            there unless the user asked to remove it.

            Include a YAML header delimited by --- with an explicit native type:
            topic, procedure, decision, reference, source, hub or untyped. Use
            tags for domain-specific terms and a one-line description (at most
            300 characters). Preserve existing unknown header fields. Never author
            title, generated, verified, status or superseded_by in the header;
            those are catalogue-derived. The rest of content_md is Markdown.

            This stores a suggestion and changes nothing in the wiki.
            """

            port = _require_port()
            found = await _resolve(path, action=f"propose an edit to '{path}'")
            if not isinstance(found, WikiPageRef):
                return found
            async with read_state_lock:
                state = read_state.get(found.slug)
                is_complete = state is not None and state.complete
                base_revision_id = state.revision if state is not None else None
            if not is_complete:
                return _resolution_failure(
                    f"You have not read all of '{path}' this turn — it is "
                    "longer than one wiki_read_page call returns, and "
                    "content_md would replace text you have not seen. Call "
                    "wiki_read_page again with the offset it gave you until "
                    "it says you have reached the end, then propose your edit."
                )
            if base_revision_id is None:
                return _resolution_failure(
                    f"Read '{path}' with wiki_read_page in this turn before "
                    "proposing an edit to it — a proposal must be anchored to "
                    "the exact text you read, and a change to the page since "
                    "your last read of it (in an earlier turn, or by someone "
                    "else) makes that anchor stale."
                )
            started = time.monotonic()
            try:
                proposal = await port.propose_edit(
                    slug=found.slug,
                    content_md=content_md,
                    base_revision_id=base_revision_id,
                )
            except Exception as exc:
                if getattr(exc, "status_code", None) == 409:
                    # base_revision_id is already stale server-side. Drop this
                    # slug's "read to the end" state so it cannot authorize
                    # another proposal before a fresh wiki_read_page — an
                    # unread retry must be refused, not just this one.
                    async with read_state_lock:
                        read_state.pop(found.slug, None)
                return _wiki_tool_failure(
                    action=f"propose an edit to '{path}'",
                    exc=exc,
                    elapsed_s=time.monotonic() - started,
                )
            return _ok(
                f"Proposal {proposal.proposal_id} prepared ({proposal.summary}). {_PREPARED}"
            )

        @tool("wiki_propose_page", response_format="content_and_artifact")
        async def wiki_propose_page(
            title: str, content_md: str, parent_path: str | None = None
        ) -> tuple[str, ToolInvocationResult]:
            """Suggest a NEW wiki page. Use wiki_propose_page_text for one that exists.

            `parent_path` nests it under an existing page, addressed the way
            wiki_read_page addresses one; omit it for a top-level page. Check
            the index first — a second page on a topic the wiki already covers
            is worse than a longer one. Two pages under the same parent cannot
            share a title, so pick one that is not already in that branch.

            Include a YAML header delimited by --- with an explicit native type:
            topic, procedure, decision, reference, source, hub or untyped. Use
            tags for domain-specific terms and a one-line description (at most
            300 characters). Preserve existing unknown header fields. Never author
            title, generated, verified, status or superseded_by in the header;
            those are catalogue-derived. The rest of content_md is Markdown.

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
            return _ok(
                f"Proposal {proposal.proposal_id} prepared ({proposal.summary}). {_PREPARED}"
            )

        @tool("wiki_propose_file", response_format="content_and_artifact")
        async def wiki_propose_file(
            document_id: str,
            title: str | None = None,
            parent_path: str | None = None,
            new_version_of: str | None = None,
        ) -> tuple[str, ToolInvocationResult]:
            """Suggest adding one of THIS conversation's files to the wiki.

            `document_id` is the file's document_id as list_conversation_files
            gives it; copy it exactly. `title` is the name it gets in the wiki,
            with its extension; omit it to keep the file's own name.
            `parent_path` places it under an existing page; omit it for the
            top level. To replace a wiki file with a new version instead, give
            that file's path as `new_version_of` (same extension; `title` and
            `parent_path` are then ignored). Its current content is copied now.

            This stores a suggestion and changes nothing in the wiki.
            """

            port = _require_port()
            action = "propose the file"
            slug: str | None = None
            parent_slug: str | None = None
            if target := new_version_of or parent_path:
                kind = "file" if new_version_of else "page"
                found = await _resolve(target, action=action, kind=kind)
                if not isinstance(found, WikiPageRef):
                    return found
                slug, parent_slug = (
                    (found.slug, None) if new_version_of else (None, found.slug)
                )
            started = time.monotonic()
            try:
                proposal = await port.propose_file(
                    document_id=document_id,
                    title=title,
                    parent_slug=parent_slug,
                    slug=slug,
                )
            except Exception as exc:
                return _wiki_tool_failure(
                    action=action, exc=exc, elapsed_s=time.monotonic() - started
                )
            return _ok(
                f"Proposal {proposal.proposal_id} prepared ({proposal.summary}). {_PREPARED}"
            )

        @tool("wiki_submit_proposal", response_format="content_and_artifact")
        async def wiki_submit_proposal(
            proposal_id: str,
        ) -> tuple[str, ToolInvocationResult]:
            """Ask the user to confirm a prepared proposal.

            The user is shown what would change and confirms or declines it.
            Call it only with an id a propose tool just gave you, and only
            once — if the user declines, do not call it again with the same id.
            """

            nonlocal tree
            port = _require_port()
            # The user decided in the approval card, before this call ran: it
            # only reads what became of the proposal.
            started = time.monotonic()
            try:
                outcome = await port.proposal_status(proposal_id)
            except Exception as exc:
                return _wiki_tool_failure(
                    action="read the proposal",
                    exc=exc,
                    elapsed_s=time.monotonic() - started,
                )
            if outcome.status != "published":
                return _ok(_SUBMIT_OUTCOMES[outcome.status])
            # Published. A failure reading the tree back must not read as a
            # failure: the model's recovery would be to submit the same id again.
            where = " (its path could not be read back)"
            try:
                async with tree_lock:
                    tree = None
                after = await _tree()
                published = next((p for p in after if p.slug == outcome.slug), None)
                if published is not None:
                    where = f" '{_page_path(after, published)}'"
            except Exception as exc:
                run_stop = unwrap_run_stop_error(exc)
                if run_stop is not None:
                    raise run_stop from None
                logger.warning(
                    "team_wiki: proposal %s published, but the tree could not "
                    "be read back to name it.",
                    proposal_id,
                )
            # The entry's ACTUAL path, not a general assurance that nothing
            # moved: an agent that believed it had moved a page restated a
            # hierarchy that did not exist.
            return _ok(
                f"Published: it is in the wiki at{where}. Publishing never "
                "moves an existing page."
            )

        return [
            wiki_list_pages,
            wiki_read_page,
            wiki_read_file,
            wiki_propose_page_text,
            wiki_propose_page,
            wiki_propose_file,
            wiki_submit_proposal,
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
