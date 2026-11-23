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

"""The `team_wiki` capability's runtime half, against a stubbed port.

Every interesting case here is a failure case: what the model is told when the
wiki refuses, when a slug is wrong, when a page is longer than the budget, and
what the prompt says when the wiki cannot be read at all. A tool that raises
takes the turn down; a tool that lies about an empty wiki is worse.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
from fred_capability_team_wiki.wiki import capability as cap_module
from fred_capability_team_wiki.wiki.capability import (
    PAGE_READ_MAX_CHARS,
    TeamWikiCapability,
    TeamWikiConfig,
    _format_page_batch,
    _TeamWikiPromptMiddleware,
)
from fred_core.security.backend_to_backend_auth import M2MAuthConfig, M2MTokenProvider
from fred_core.security.delegation import DelegationConfig
from fred_runtime.common.outbound_credentials import DelegationRuntime, RunRecord
from fred_runtime.integrations.v2_runtime.adapters import TeamWikiAdapter
from fred_runtime.runtime_support.authority import (
    AuthorityLostError,
    DelegationUnavailableError,
)
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
)
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
    ToolFailure,
    ToolFailureCode,
)
from fred_sdk.contracts.runtime import (
    RunStopError,
    RuntimeServices,
    TeamWikiPort,
    TeamWikiPortError,
    WikiFileUnreadableError,
    WikiPageContent,
    WikiPageRef,
    WikiProposalRef,
    WikiProposalStatus,
    WikiSearchHit,
    WikiSearchResult,
)
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel


class _FakePort(TeamWikiPort):
    def __init__(
        self,
        *,
        pages: tuple[WikiPageRef, ...] = (),
        content: str = "",
        rules: str = "",
        revision_id: str = "rev-1",
        raises: Exception | None = None,
    ) -> None:
        self._pages = pages
        self._content = content
        self._rules = rules
        self._revision_id = revision_id
        self._raises = raises
        self.search_result = WikiSearchResult(
            hits=(), next_offset=None, truncated=False
        )
        self.search_calls: list[tuple[Any, ...]] = []
        self.list_calls = 0
        self.rules_calls = 0
        self.proposed: list[tuple[str, str]] = []
        self.propose_bases: list[str] = []
        self.published: list[str] = []
        self.proposed_files: list[tuple[Any, ...]] = []
        # What the next status read reports, and where a published proposal
        # lands (an existing page for an edit, a new one for a creation).
        self.status: Any = "published"
        self.publish_slug = "some-slug"
        self.publish_title = "Some Page"
        # Fails only `list_pages`, so a test can break the tree read back
        # AFTER a write has already landed.
        self.raise_on_list: Exception | None = None
        # Fails only the next `propose_edit`, so a test can simulate the
        # server's 409 (base_revision_id went stale) without also breaking
        # the reads that lead up to it.
        self.raise_on_propose_edit: Exception | None = None

    async def search(
        self,
        query: str,
        *,
        page_type: str | None = None,
        tag: str | None = None,
        offset: int = 0,
    ) -> WikiSearchResult:
        if self._raises is not None:
            raise self._raises
        self.search_calls.append((query, page_type, tag, offset))
        return self.search_result

    async def list_pages(self) -> tuple[WikiPageRef, ...]:
        self.list_calls += 1
        if self.raise_on_list is not None:
            raise self.raise_on_list
        if self._raises is not None:
            raise self._raises
        return self._pages

    def set_pages(self, pages: tuple[WikiPageRef, ...]) -> None:
        """A change landing between two calls in one turn."""

        self._pages = pages

    def set_content(self, content: str, *, revision_id: str) -> None:
        """A page edited — by a human, or another turn — between two
        continuation reads of the same slug in this turn."""

        self._content = content
        self._revision_id = revision_id

    async def read_page(
        self, slug: str, *, max_chars: int = 8_000, offset: int = 0
    ) -> WikiPageContent:
        if self._raises is not None:
            raise self._raises
        total = len(self._content)
        start = max(offset, 0)
        end = min(start + max_chars, total)
        next_offset = end if end < total else None
        return WikiPageContent(
            slug=slug,
            title=slug.title(),
            content_md=self._content[start:end],
            truncated=next_offset is not None,
            revision_id=self._revision_id,
            offset=start,
            next_offset=next_offset,
            total_chars=total,
        )

    async def read_rules(self) -> str:
        self.rules_calls += 1
        if self._raises is not None:
            raise self._raises
        return self._rules

    async def propose_page(
        self, *, title: str, content_md: str, parent_slug: str | None = None
    ) -> WikiProposalRef:
        if self._raises is not None:
            raise self._raises
        self.proposed.append((title, content_md))
        return WikiProposalRef(
            proposal_id="prop-1", title=title, summary=f"create “{title}”"
        )

    async def propose_edit(
        self, *, slug: str, content_md: str, base_revision_id: str
    ) -> WikiProposalRef:
        if self._raises is not None:
            raise self._raises
        if self.raise_on_propose_edit is not None:
            exc, self.raise_on_propose_edit = self.raise_on_propose_edit, None
            raise exc
        self.proposed.append((slug, content_md))
        self.propose_bases.append(base_revision_id)
        return WikiProposalRef(
            proposal_id="prop-2", title=slug, slug=slug, summary=f"rewrite “{slug}”"
        )

    async def read_file(
        self, slug: str, *, max_chars: int = 8_000, offset: int = 0
    ) -> WikiPageContent:
        if not slug.endswith(".csv"):
            raise WikiFileUnreadableError("not text")
        return await self.read_page(slug, max_chars=max_chars, offset=offset)

    async def propose_file(
        self,
        *,
        document_id: str,
        title: str | None = None,
        parent_slug: str | None = None,
        slug: str | None = None,
    ) -> WikiProposalRef:
        self.proposed_files.append((document_id, title, parent_slug, slug))
        return WikiProposalRef(
            proposal_id="prop-3", title=title or "f.csv", summary="add the file"
        )

    async def proposal_status(self, proposal_id: str) -> WikiProposalStatus:
        if self._raises is not None:
            raise self._raises
        self.published.append(proposal_id)
        # An accepted proposal changes the tree, and the tool re-reads it to
        # name where the entry is. A fake that published into nothing would let
        # the "it is in the wiki at <path>" wording pass untested.
        if self.status == "published" and all(
            page.slug != self.publish_slug for page in self._pages
        ):
            self._pages = (
                *self._pages,
                _page(self.publish_slug, self.publish_title),
            )
        return WikiProposalStatus(
            proposal_id=proposal_id, status=self.status, slug=self.publish_slug
        )


def _ctx(port: TeamWikiPort | None, mode: str = "read") -> Any:
    return CapabilityContext(
        identity=CapabilityIdentity(user_id="u", session_id="s"),
        config=TeamWikiConfig(mode=mode),
        turn_options=EmptyModel(),
        services=RuntimeServices(team_wiki=port),
    )


def _tools(port: TeamWikiPort | None, mode: str = "read") -> dict[str, Any]:
    return {t.name: t for t in TeamWikiCapability().tools(_ctx(port, mode))}


def _call(
    port: TeamWikiPort | None,
    name: str,
    args: dict[str, Any],
    tools: dict[str, Any] | None = None,
    mode: str = "read_write",
) -> Any:
    """Invoke through a ToolCall, so a `content_and_artifact` tool hands back
    the ToolMessage the runtime actually sees (content + artifact), not the
    raw tuple. Pass `tools` to make several calls against ONE binding, the way
    a single turn does — a fresh binding has a fresh per-turn state."""

    the_tool = (tools or _tools(port, mode))[name]
    return asyncio.run(
        the_tool.ainvoke({"type": "tool_call", "name": name, "args": args, "id": "c1"})
    )


def _page(slug: str, title: str, parent: str | None = None) -> WikiPageRef:
    kind = "file" if "." in title else "page"
    return WikiPageRef(
        page_id=slug, slug=slug, title=title, parent_slug=parent, kind=kind
    )


def test_listing_shows_full_paths_and_no_identifier() -> None:
    """`wiki_list_pages` renders full paths, not indentation (WIKI-05): a
    paginated slice does not always start at the root, so a page's ancestors
    are not necessarily in the same slice to lean on for hierarchy — the
    path carries that on every line regardless of where a boundary falls."""

    port = _FakePort(
        pages=(
            _page("6adb844e", "Onboarding"),
            _page("21b89ad9", "Tooling", parent="6adb844e"),
        )
    )
    text = _call(port, "wiki_list_pages", {}).content

    assert "- Onboarding" in text
    assert "- Onboarding / Tooling" in text
    assert "6adb844e" not in text
    assert "21b89ad9" not in text


def test_the_index_never_shows_a_slug() -> None:
    """A model that can see an opaque id prints it to a user who has no use for
    it, and asking it not to does not hold — anything in the context can come
    back out. So the id stays out of the context."""

    port = _FakePort(pages=(_page("2dc58e80", "Les Shinigamis"),))
    text = _call(port, "wiki_list_pages", {}).content

    assert "Les Shinigamis" in text
    assert "2dc58e80" not in text


def test_an_empty_wiki_says_so_rather_than_returning_nothing() -> None:
    text = _call(_FakePort(), "wiki_list_pages", {}).content

    assert "no pages yet" in text


# ── pagination (WIKI-05): the index's own truncation used to send the model to
# wiki_list_pages for "the rest", and that tool returned the identical
# truncated prefix — the omitted pages were unreachable by any tool. ─────────


def test_finite_calls_discover_every_page_with_no_skip_or_repeat() -> None:
    """Follow the offset the tool hands back, call after call, until it says
    there is nothing more. Every page must be seen, none twice."""

    pages = tuple(_page(f"s{i}", f"Page {i}") for i in range(1_000))
    port = _FakePort(pages=pages)
    turn = _tools(port)

    seen: list[str] = []
    offset = 0
    calls = 0
    while True:
        calls += 1
        assert calls <= len(pages) + 2, "pagination did not terminate"
        text = _call(port, "wiki_list_pages", {"offset": offset}, turn).content
        body_lines = text.splitlines()[1:]
        seen.extend(
            line.removeprefix("- ") for line in body_lines if line.startswith("- ")
        )
        match = re.search(r"offset=(\d+) to continue", text)
        if match is None:
            break
        offset = int(match.group(1))

    assert seen == [p.title for p in pages]
    assert calls > 1, "the fixture should not fit in a single call"


def test_an_out_of_range_offset_says_there_is_nothing_more() -> None:
    port = _FakePort(pages=(_page("a", "A"),))
    text = _call(port, "wiki_list_pages", {"offset": 50}).content

    assert "no more pages" in text
    assert "total=1" in text


def test_a_negative_offset_is_treated_as_the_start() -> None:
    port = _FakePort(pages=(_page("a", "A"), _page("b", "B")))
    text = _call(port, "wiki_list_pages", {"offset": -5}).content

    assert "- A" in text
    assert "offset=0" in text


def test_every_call_refreshes_the_tree() -> None:
    """A continuation call re-fetches too, not only offset 0: caching a slice
    across calls once meant a same-turn publish (which always refreshes)
    could reorder the list underneath an old offset, silently skipping or
    duplicating pages — see the regression test below."""

    pages = tuple(_page(f"s{i}", f"Page {i}") for i in range(200))
    port = _FakePort(pages=pages)
    turn = _tools(port)

    _call(port, "wiki_list_pages", {"offset": 0}, turn)
    assert port.list_calls == 1
    _call(port, "wiki_list_pages", {"offset": 50}, turn)
    assert port.list_calls == 2


def test_a_publish_between_pagination_calls_does_not_hide_the_new_page() -> None:
    """List page 1, publish a new page, then continue with the offset page 1
    handed back. The new page must still turn up somewhere in the rest of
    the listing, not fall into a gap the stale offset skips over."""

    pages = tuple(_page(f"s{i}", f"Page {i}") for i in range(1_000))
    port = _FakePort(pages=pages)
    port.publish_title = "New Page"
    turn = _tools(port, "read_write")

    first = _call(port, "wiki_list_pages", {"offset": 0}, turn)
    match = re.search(r"offset=(\d+) to continue", first.content)
    assert match is not None, "the fixture should not fit in a single call"
    next_offset = int(match.group(1))

    _call(port, "wiki_propose_page", {"title": "New Page", "content_md": "x"}, turn)
    _call(port, "wiki_submit_proposal", {"proposal_id": "prop-1"}, turn)

    seen: list[str] = []
    offset = next_offset
    while True:
        text = _call(port, "wiki_list_pages", {"offset": offset}, turn).content
        body_lines = text.splitlines()[1:]
        seen.extend(
            line.removeprefix("- ") for line in body_lines if line.startswith("- ")
        )
        match = re.search(r"offset=(\d+) to continue", text)
        if match is None:
            break
        offset = int(match.group(1))

    assert "New Page" in seen


def test_a_single_pathologically_long_title_still_advances() -> None:
    """A page whose own path alone exceeds the per-call budget must still be
    returned, and the offset must still move past it — otherwise pagination
    stalls forever on that one page."""

    huge_title = "X" * 20_000
    pages = (_page("a", huge_title), _page("b", "Short"))
    body, next_offset = _format_page_batch(pages, offset=0)

    assert huge_title in body
    assert next_offset == 1
    # And the second call reaches the end cleanly.
    body2, next_offset2 = _format_page_batch(pages, offset=next_offset)
    assert "Short" in body2
    assert next_offset2 is None


def test_pagination_boundary_is_exact_when_pages_fit_precisely() -> None:
    """When the last page in a slice lands exactly on the budget, there must
    be no phantom continuation offered, and no page dropped either."""

    pages = (_page("a", "A"), _page("b", "B"))
    line_len = len(f"- {pages[1].title}") + 1
    budget = len(f"- {pages[0].title}") + 1 + line_len

    original = cap_module.LIST_PAGES_MAX_CHARS
    cap_module.LIST_PAGES_MAX_CHARS = budget
    try:
        body, next_offset = _format_page_batch(pages, offset=0)
    finally:
        cap_module.LIST_PAGES_MAX_CHARS = original

    assert "- A" in body and "- B" in body
    assert next_offset is None


def test_a_page_whose_parent_was_shown_in_an_earlier_call_stays_addressable() -> None:
    """A later slice must not lose the hierarchy just because the parent was
    only shown in an earlier call: the full path carries it on every line."""

    pages = (_page("a", "Parent"), _page("b", "Child", parent="a"))
    body, _ = _format_page_batch(pages, offset=1)

    assert body == "- Parent / Child"


def test_a_refusal_carries_the_server_own_reason() -> None:
    """403 covers two very different refusals — the capability being off, and
    the rules page being out of reach — so the message the server sent is what
    reaches the model, not a guess made from the status."""

    port = _FakePort(
        pages=(_page("s1", "X"),),
        raises=TeamWikiPortError(
            "The rules page cannot be changed by an agent.", status_code=403
        ),
    )
    message = _call(port, "wiki_read_page", {"path": "X"})

    assert message.artifact.failure == ToolFailure(
        code=ToolFailureCode.resource_unavailable, status=403
    )
    assert "not allowed" in message.content
    assert "rules page cannot be changed by an agent" in message.content


def test_an_unknown_path_is_an_error_not_an_empty_page() -> None:
    """Handing back an empty page would have the model report the topic as
    undocumented — a confident answer built on a page that does not exist."""

    port = _FakePort(pages=(_page("s1", "Onboarding"),))
    message = _call(port, "wiki_read_page", {"path": "Ghost"})

    assert message.artifact.failure == ToolFailure(
        code=ToolFailureCode.resource_unavailable
    )
    assert "no wiki page at 'Ghost'" in message.content
    # Says how to address one, since that is the mistake being made.
    assert "Parent page / Child page" in message.content


def test_an_ambiguous_path_lists_the_candidates_instead_of_guessing() -> None:
    """Sibling titles are refused, so a FULL path is unique — but a bare title
    can still match two pages in different branches. Picking one silently would
    have the model answer about a page the user did not mean."""

    port = _FakePort(
        pages=(
            _page("a", "Ventes"),
            _page("b", "Achats"),
            _page("c", "Espagne", parent="a"),
            _page("d", "Espagne", parent="b"),
        )
    )
    message = _call(port, "wiki_read_page", {"path": "Espagne"})

    assert message.artifact.failure == ToolFailure(
        code=ToolFailureCode.invalid_arguments
    )
    assert "Ventes / Espagne" in message.content
    assert "Achats / Espagne" in message.content


def test_a_full_path_resolves_where_a_bare_title_is_ambiguous() -> None:
    port = _FakePort(
        pages=(
            _page("a", "Ventes"),
            _page("b", "Achats"),
            _page("c", "Espagne", parent="a"),
            _page("d", "Espagne", parent="b"),
        ),
        content="body",
    )
    message = _call(port, "wiki_read_page", {"path": "Ventes / Espagne"})

    assert message.artifact.is_error is False
    assert "body" in message.content


def test_a_long_page_comes_back_cut_and_says_more_remains() -> None:
    port = _FakePort(
        pages=(_page("s1", "Big"),), content="x" * (PAGE_READ_MAX_CHARS + 500)
    )
    message = _call(port, "wiki_read_page", {"path": "Big"})

    assert message.artifact.is_error is False
    assert "MORE TEXT REMAINS" in message.content
    assert f"offset={PAGE_READ_MAX_CHARS}" in message.content


def test_continuation_reaches_the_end_and_says_so() -> None:
    port = _FakePort(
        pages=(_page("s1", "Big"),), content="a" * PAGE_READ_MAX_CHARS + "TAIL"
    )
    turn = _tools(port)

    first = _call(port, "wiki_read_page", {"path": "Big"}, turn).content
    assert "TAIL" not in first

    second = _call(
        port, "wiki_read_page", {"path": "Big", "offset": PAGE_READ_MAX_CHARS}, turn
    ).content

    assert "TAIL" in second
    assert "End reached" in second


def test_replaying_the_last_completed_offset_is_not_refused() -> None:
    """A retry of the exact call that just finished the read (e.g. after a
    dropped tool result) must succeed, not be treated as skipping ahead."""

    port = _FakePort(
        pages=(_page("s1", "Big"),), content="a" * PAGE_READ_MAX_CHARS + "TAIL"
    )
    turn = _tools(port)
    _call(port, "wiki_read_page", {"path": "Big"}, turn)
    _call(port, "wiki_read_page", {"path": "Big", "offset": PAGE_READ_MAX_CHARS}, turn)

    replay = _call(
        port, "wiki_read_page", {"path": "Big", "offset": PAGE_READ_MAX_CHARS}, turn
    )

    assert replay.artifact.is_error is False
    assert "TAIL" in replay.content


def test_an_overlapping_offset_within_covered_range_is_not_refused() -> None:
    """An offset that re-reads ground already covered — not a skip-ahead — is
    allowed; only skipping past the covered frontier is refused."""

    port = _FakePort(
        pages=(_page("s1", "Big"),), content="a" * PAGE_READ_MAX_CHARS + "TAIL"
    )
    turn = _tools(port)
    _call(port, "wiki_read_page", {"path": "Big"}, turn)

    overlap = _call(
        port,
        "wiki_read_page",
        {"path": "Big", "offset": PAGE_READ_MAX_CHARS - 10},
        turn,
    )

    assert overlap.artifact.is_error is False


def test_a_continuation_offset_that_does_not_match_is_refused() -> None:
    """A model guessing at an offset it never earned — too far, or on a page
    it never started reading — must not be handed an arbitrary slice."""

    port = _FakePort(
        pages=(_page("s1", "Big"),), content="x" * (PAGE_READ_MAX_CHARS + 500)
    )
    message = _call(port, "wiki_read_page", {"path": "Big", "offset": 500})

    assert message.artifact.is_error is True
    assert "was not read up to offset 500" in message.content


def test_a_revision_change_mid_read_is_detected_and_refused() -> None:
    """The tail of a page changed under the model between two continuation
    calls. Handing over the new tail as if it continued the old head would
    silently splice two different revisions into one document."""

    port = _FakePort(
        pages=(_page("s1", "Big"),),
        content="a" * PAGE_READ_MAX_CHARS + "OLD-TAIL",
        revision_id="rev-1",
    )
    turn = _tools(port, "read_write")
    _call(port, "wiki_read_page", {"path": "Big"}, turn)

    port.set_content("b" * PAGE_READ_MAX_CHARS + "NEW-TAIL", revision_id="rev-2")
    second = _call(
        port, "wiki_read_page", {"path": "Big", "offset": PAGE_READ_MAX_CHARS}, turn
    )

    assert second.artifact.is_error is True
    assert "changed while you were reading it" in second.content

    # The half-read session is discarded — proposing must still be refused.
    refusal = _call(
        port, "wiki_propose_page_text", {"path": "Big", "content_md": "new"}, turn
    )
    assert refusal.artifact.is_error is True
    assert port.proposed == []


def test_a_restart_on_a_new_revision_does_not_inherit_stale_coverage() -> None:
    """A2: A (16 000 chars = two 8 000-char segments) is read whole, then B
    (24 000 chars) replaces it before a restart read at offset 0. The restart
    landing on B must not let A's leftover coverage (16 000) let a later call
    skip straight past the [8 000, 16 000) segment of B that was never read."""

    port = _FakePort(
        pages=(_page("s1", "Big"),),
        content="a" * (2 * PAGE_READ_MAX_CHARS),
        revision_id="rev-A",
    )
    turn = _tools(port, "read_write")
    _call(port, "wiki_read_page", {"path": "Big"}, turn)
    _call(port, "wiki_read_page", {"path": "Big", "offset": PAGE_READ_MAX_CHARS}, turn)

    port.set_content("b" * (3 * PAGE_READ_MAX_CHARS), revision_id="rev-B")
    _call(port, "wiki_read_page", {"path": "Big"}, turn)  # offset=0 restart, lands on B

    jump = _call(
        port,
        "wiki_read_page",
        {"path": "Big", "offset": 2 * PAGE_READ_MAX_CHARS},
        turn,
    )
    assert jump.artifact.is_error is True

    # Only after actually reading the missing middle segment of B does
    # completion — and therefore a propose — become legitimate.
    _call(port, "wiki_read_page", {"path": "Big", "offset": PAGE_READ_MAX_CHARS}, turn)
    _call(
        port,
        "wiki_read_page",
        {"path": "Big", "offset": 2 * PAGE_READ_MAX_CHARS},
        turn,
    )
    ok = _call(
        port, "wiki_propose_page_text", {"path": "Big", "content_md": "new"}, turn
    )
    assert ok.artifact.is_error is False
    assert port.propose_bases == ["rev-B"]


def test_a_missing_port_fails_loud() -> None:
    """A bare harness must not look like an empty wiki."""

    with pytest.raises(RuntimeError):
        _call(None, "wiki_list_pages", {})


def test_the_prompt_block_carries_the_rules_and_the_index() -> None:
    port = _FakePort(pages=(_page("onboarding", "Onboarding"),), rules="Never guess.")
    block = asyncio.run(_TeamWikiPromptMiddleware(port, can_write=False)._compose())

    assert "Never guess." in block
    assert "- Onboarding" in block
    assert "never act against them" in block
    # The block used to tell the model the index carried titles only, which
    # stopped being true when slugs went into it — and a model that believes
    # it has no slug builds one out of the title.
    assert "titles only" not in block
    assert "path in the index" in block


def test_the_prompt_block_is_fetched_once_per_turn() -> None:
    """A ReAct turn calls the model once per tool round. Re-reading the wiki on
    each would put two control-plane round-trips on the latency path of every
    round, to fetch text that cannot have changed."""

    port = _FakePort(pages=(_page("a", "A"),), rules="r")
    middleware = _TeamWikiPromptMiddleware(port, can_write=False)

    async def three_calls() -> None:
        await asyncio.gather(
            middleware._wiki_block(),
            middleware._wiki_block(),
            middleware._wiki_block(),
        )

    asyncio.run(three_calls())

    assert port.list_calls == 1
    assert port.rules_calls == 1


def test_an_unreachable_wiki_does_not_take_the_turn_down() -> None:
    """But it must not read as "this team has no rules" either — the block says
    the wiki could not be read, and the tools report the same failure."""

    port = _FakePort(raises=TeamWikiPortError("boom", status_code=503))
    block = asyncio.run(_TeamWikiPromptMiddleware(port, can_write=False)._compose())

    assert "could not be read this turn" in block
    assert "Do not state or imply what it contains" in block


# ---------------------------------------------------------------------------
# Field evidence, session bbd9ebc3 (2026-09-07)
#
# Asked to add a fact to a page, an agent read the page, found no way to write,
# re-read it five more times, then answered "Mise à jour appliquée" with the new
# Markdown. Nothing was written. The user had every reason to believe the wiki
# had changed — the worst failure a knowledge base can have.
# ---------------------------------------------------------------------------


def test_the_prompt_block_says_the_wiki_cannot_be_written() -> None:
    """Told only that it "has access to the wiki", a model asked to edit one
    will narrate the edit as done. The block has to close that off."""

    port = _FakePort(pages=(_page("a", "A"),))
    block = asyncio.run(_TeamWikiPromptMiddleware(port, can_write=False)._compose())

    assert "You cannot change it" in block
    assert "Never say a page has been updated" in block


def test_reading_the_same_page_twice_in_a_turn_says_to_stop() -> None:
    """The content still comes back — a trimmed history can legitimately cost
    the model a page it read — but the second answer says re-reading changes
    nothing, which is what the loop was waiting to hear."""

    port = _FakePort(pages=(_page("s1", "Shinigami"),), content="Some content.")
    turn = _tools(port)

    first = _call(port, "wiki_read_page", {"path": "Shinigami"}, turn).content
    assert "already read this page" not in first

    second = _call(port, "wiki_read_page", {"path": "Shinigami"}, turn).content
    assert "Some content." in second
    assert "already read this page" in second
    assert "reading it again will not change it" in second


# ---------------------------------------------------------------------------
# The write half (WIKI-04)
# ---------------------------------------------------------------------------


def test_read_mode_exposes_no_way_to_change_the_wiki() -> None:
    """The mode is the whole gate on the tool surface. An agent left on the
    default must not be one config read away from writing into the team's
    shared memory."""

    assert set(_tools(_FakePort())) == {
        "wiki_list_pages",
        "wiki_search",
        "wiki_read_page",
        "wiki_read_file",
    }


def test_read_write_mode_adds_proposing_and_publishing_only() -> None:
    """And nothing else, ever: no delete, rename or move tool exists here. The
    RFC's §5.4 invariant is an absence, not a check that could be bypassed."""

    names = set(_tools(_FakePort(), "read_write"))

    assert names == {
        "wiki_list_pages",
        "wiki_search",
        "wiki_read_page",
        "wiki_read_file",
        "wiki_propose_page_text",
        "wiki_propose_page",
        "wiki_propose_file",
        "wiki_submit_proposal",
    }
    assert not any("delete" in n or "rename" in n or "move" in n for n in names)


def test_only_publishing_is_gated_for_approval() -> None:
    """Gating the propose tools would ask the user to approve a draft they
    cannot see yet: the gate runs before the tool and carries only a truncated
    argument preview. The proposal is stored first so the modal has something
    to diff."""

    specs = TeamWikiCapability().hitl_specs()

    assert [s.tool for s in specs] == ["wiki_submit_proposal"]
    assert specs[0].require is True


def test_a_published_proposal_is_reported_at_its_actual_path() -> None:
    """Field evidence, 2026-09-07: asked to MOVE two pages, an agent re-proposed
    each page's existing text, published both, and reported the move done — a
    bare "Published" was all it had to go on. The result names the path."""

    port = _FakePort(pages=(_page("s1", "S"),))
    port.publish_slug = "s1"
    message = _call(port, "wiki_submit_proposal", {"proposal_id": "prop-2"})

    assert port.published == ["prop-2"]
    assert "in the wiki at 'S'" in message.content
    assert "never moves" in message.content


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("pending", "waits for an editor"),
        ("draft", "has not confirmed"),
        ("closed", "no longer pending"),
    ],
)
def test_submitting_only_reports_what_the_person_decided(
    status: str, expected: str
) -> None:
    """The person confirms or declines in the card, with their own token; the
    tool only reads the outcome back, and never claims a publication."""

    port = _FakePort()
    port.status = status
    message = _call(port, "wiki_submit_proposal", {"proposal_id": "prop-2"})

    assert message.artifact.is_error is False
    assert expected in message.content
    assert "Published" not in message.content


def test_a_path_naming_a_parent_never_falls_back_to_another_branch() -> None:
    """ "Archive / Onboarding" answered with "HR / Onboarding" — a different
    page, whose whole text a write would then have replaced."""

    port = _FakePort(
        pages=(
            _page("a", "HR"),
            _page("b", "Archive"),
            _page("c", "Onboarding", parent="a"),
        )
    )
    message = _call(port, "wiki_read_page", {"path": "Archive / Onboarding"})

    assert message.artifact.is_error is True
    assert "no wiki page at" in message.content


def test_a_title_containing_a_separator_is_still_addressable() -> None:
    """Titles are free text. Folding the separator on only one side left a
    page no tool could reach."""

    port = _FakePort(pages=(_page("a", "Q1/Q2"),), content="body")
    message = _call(port, "wiki_read_page", {"path": "Q1/Q2"})

    assert message.artifact.is_error is False
    assert "body" in message.content


def test_a_failed_read_back_after_publishing_is_not_reported_as_a_failure() -> None:
    """The write has landed by then. Reporting failure invites the model to
    publish the same id again, which the tool tells it never to do."""

    port = _FakePort(pages=(_page("s1", "S"),))
    port.publish_slug = "s1"
    turn = _tools(port, "read_write")
    _call(port, "wiki_read_page", {"path": "S"}, turn)
    _call(port, "wiki_propose_page_text", {"path": "S", "content_md": "new"}, turn)
    port.raise_on_list = TeamWikiPortError("down", status_code=503)
    message = _call(port, "wiki_submit_proposal", {"proposal_id": "prop-2"}, turn)

    assert message.artifact.is_error is False
    assert "Published" in message.content


def test_listing_the_pages_refreshes_what_a_path_resolves_against() -> None:
    """The docstring tells the model to list after a change; a refresh that did
    not reach the resolver answered "no such page" for a page just listed."""

    port = _FakePort(pages=(_page("a", "Old"),), content="body")
    turn = _tools(port, "read_write")
    _call(port, "wiki_read_page", {"path": "Old"}, turn)

    port.set_pages((_page("a", "Old"), _page("b", "Fresh")))
    _call(port, "wiki_list_pages", {}, turn)
    message = _call(port, "wiki_read_page", {"path": "Fresh"}, turn)

    assert message.artifact.is_error is False


def test_the_text_tool_is_named_for_its_scope() -> None:
    """The tool name is read on every call decision, which makes it a stronger
    channel than the prompt. `wiki_propose_edit` read as covering a
    reorganisation, and in the field an agent used it for one."""

    names = set(_tools(_FakePort(), "read_write"))

    assert "wiki_propose_page_text" in names
    assert "wiki_propose_edit" not in names


def test_the_write_prompt_refuses_moving_and_orders_parent_before_child() -> None:
    """Both failures the field trace showed: an agent that thought editing a
    page would move it, and one that named a parent it had not published."""

    port = _FakePort(pages=(_page("s1", "S"),), rules="r")
    block = asyncio.run(_TeamWikiPromptMiddleware(port, can_write=True)._compose())

    assert "editing its text will not move it" in block
    assert "parent published first" in block


def test_proposing_says_plainly_that_nothing_is_written_yet() -> None:
    """The model has to know its work is not done, or it reports the change as
    made — which is exactly what happened before the write path existed."""

    port = _FakePort(pages=(_page("s1", "S"),))
    turn = _tools(port, "read_write")
    _call(port, "wiki_read_page", {"path": "S"}, turn)
    message = _call(
        port, "wiki_propose_page_text", {"path": "S", "content_md": "new"}, turn
    )

    # Addressed by path; the port still receives the slug it has always taken.
    assert port.proposed == [("s1", "new")]
    assert port.published == []
    assert "Nothing is written yet" in message.content
    assert "wiki_submit_proposal" in message.content


def test_proposing_anchors_to_the_revision_just_read() -> None:
    """The base sent to the port must be what this turn's read actually
    returned, never guessed or omitted — the fix this correction makes."""

    port = _FakePort(pages=(_page("s1", "S"),), revision_id="rev-42")
    turn = _tools(port, "read_write")
    _call(port, "wiki_read_page", {"path": "S"}, turn)
    _call(port, "wiki_propose_page_text", {"path": "S", "content_md": "new"}, turn)

    assert port.propose_bases == ["rev-42"]


def test_proposing_after_only_a_partial_read_is_refused() -> None:
    """A truncated read must never be mistaken for the whole page — the exact
    mismatch this correction closes: content_md replaces a page whole, and a
    model that only saw the first segment has not seen what it would delete."""

    port = _FakePort(
        pages=(_page("s1", "Big"),), content="x" * (PAGE_READ_MAX_CHARS + 500)
    )
    turn = _tools(port, "read_write")
    _call(port, "wiki_read_page", {"path": "Big"}, turn)

    message = _call(
        port, "wiki_propose_page_text", {"path": "Big", "content_md": "new"}, turn
    )

    assert message.artifact.is_error is True
    assert "have not read all of" in message.content
    assert port.proposed == []


def test_proposing_after_reading_to_the_end_across_segments_succeeds() -> None:
    port = _FakePort(
        pages=(_page("s1", "Big"),),
        content="a" * PAGE_READ_MAX_CHARS + "TAIL",
        revision_id="rev-9",
    )
    turn = _tools(port, "read_write")
    _call(port, "wiki_read_page", {"path": "Big"}, turn)
    _call(port, "wiki_read_page", {"path": "Big", "offset": PAGE_READ_MAX_CHARS}, turn)

    message = _call(
        port, "wiki_propose_page_text", {"path": "Big", "content_md": "new"}, turn
    )

    assert message.artifact.is_error is False
    assert port.proposed == [("s1", "new")]
    assert port.propose_bases == ["rev-9"]


def test_a_conflict_on_propose_forces_a_fresh_read_before_a_retry() -> None:
    """A1: the server 409s a propose because the page moved since this turn's
    read. That stale "read to the end" state must not survive the conflict —
    an unread retry has to be refused too, not just the one that 409'd."""

    port = _FakePort(pages=(_page("s1", "S"),), content="old", revision_id="rev-1")
    port.raise_on_propose_edit = TeamWikiPortError("stale", status_code=409)
    turn = _tools(port, "read_write")
    _call(port, "wiki_read_page", {"path": "S"}, turn)

    conflict = _call(
        port, "wiki_propose_page_text", {"path": "S", "content_md": "new"}, turn
    )
    assert conflict.artifact.is_error is True
    assert port.proposed == []

    # No re-read yet: retrying on the same (now-invalidated) session must be
    # refused locally, not sent to the port a second time.
    retry = _call(
        port, "wiki_propose_page_text", {"path": "S", "content_md": "new"}, turn
    )
    assert retry.artifact.is_error is True
    assert port.proposed == []

    # Only a fresh read of the new revision can authorize a proposal again.
    port.set_content("new-base", revision_id="rev-2")
    _call(port, "wiki_read_page", {"path": "S"}, turn)
    ok = _call(port, "wiki_propose_page_text", {"path": "S", "content_md": "new"}, turn)
    assert ok.artifact.is_error is False
    assert port.propose_bases == ["rev-2"]


def test_proposing_without_reading_first_is_refused_locally() -> None:
    """A model that never read the page this turn has no revision to anchor
    on. Refusing here — before the port is even called — is what stops a
    proposal being silently created against "whatever is current"."""

    port = _FakePort(pages=(_page("s1", "S"),))
    message = _call(port, "wiki_propose_page_text", {"path": "S", "content_md": "new"})

    assert message.artifact.is_error is True
    assert "wiki_read_page" in message.content
    assert port.proposed == []


def test_a_text_file_is_read_and_another_format_is_reported_unreadable() -> None:
    port = _FakePort(
        pages=(_page("a.csv", "a.csv"), _page("b.pdf", "b.pdf")), content="x,y"
    )
    turn = _tools(port)

    text = _call(port, "wiki_read_file", {"path": "a.csv"}, turn)
    pdf = _call(port, "wiki_read_file", {"path": "b.pdf"}, turn)

    assert "x,y" in text.content and "End reached" in text.content
    assert pdf.artifact.is_error is True
    assert "md, csv, txt and json" in pdf.content


def test_a_file_is_not_read_as_a_page_nor_used_as_a_parent() -> None:
    port = _FakePort(pages=(_page("a.csv", "a.csv"),))

    page = _call(port, "wiki_read_page", {"path": "a.csv"})
    parent = _call(
        port, "wiki_propose_file", {"document_id": "d-1", "parent_path": "a.csv"}
    )

    assert "wiki_read_file" in page.content
    assert parent.artifact.is_error is True
    assert port.proposed_files == []


def test_proposing_a_file_names_the_conversation_file_and_its_parent() -> None:
    port = _FakePort(pages=(_page("s1", "S"),))
    message = _call(
        port,
        "wiki_propose_file",
        {"document_id": "d-1", "title": "t.csv", "parent_path": "S"},
    )

    assert port.proposed_files == [("d-1", "t.csv", "s1", None)]
    assert "Nothing is written yet" in message.content
    assert "wiki_submit_proposal" in message.content


def test_a_new_version_names_the_wiki_file_it_replaces() -> None:
    port = _FakePort(pages=(_page("s1", "S"), _page("f", "f.csv", parent="s1")))
    message = _call(
        port, "wiki_propose_file", {"document_id": "d-1", "new_version_of": "S / f.csv"}
    )

    assert message.artifact.is_error is False
    assert port.proposed_files == [("d-1", None, None, "f")]


def test_the_write_mode_prompt_describes_the_two_steps() -> None:
    port = _FakePort(pages=(_page("a", "A"),))
    block = asyncio.run(_TeamWikiPromptMiddleware(port, can_write=True)._compose())

    assert "wiki_submit_proposal" in block
    assert "replaces it whole" in block
    assert "never change the rules page" in block
    # The read-only wording must NOT survive into write mode: it would tell an
    # agent that can write that it cannot.
    assert "You cannot change it" not in block


# ---------------------------------------------------------------------------
# A run stop is not a wiki failure: it ends the run instead of becoming text
# ---------------------------------------------------------------------------

UPSTREAM_MARKER = "upstream-detail-marker"
WORKLOAD_SECRET_ENV = "FRED_TEST_WORKLOAD_SECRET"  # pragma: allowlist secret


def _chained(stop: RunStopError) -> TeamWikiPortError:
    """The runtime adapter's shape: its port error, raised from the stop."""

    try:
        raise TeamWikiPortError(str(stop)) from stop
    except TeamWikiPortError as wrapper:
        return wrapper


def _failing(error: Exception) -> Callable[..., Awaitable[Any]]:
    async def _raise(*_args: Any, **_kwargs: Any) -> Any:
        raise error

    return _raise


Scenario = Callable[[_FakePort, Exception, pytest.MonkeyPatch], Any]


def _listing(port: _FakePort, error: Exception, _mp: pytest.MonkeyPatch) -> Any:
    port.raise_on_list = error
    return _call(port, "wiki_list_pages", {})


def _resolving(port: _FakePort, error: Exception, _mp: pytest.MonkeyPatch) -> Any:
    port.raise_on_list = error
    return _call(port, "wiki_read_page", {"path": "S"})


def _reading(port: _FakePort, error: Exception, mp: pytest.MonkeyPatch) -> Any:
    mp.setattr(port, "read_page", _failing(error))
    return _call(port, "wiki_read_page", {"path": "S"})


def _proposing_text(port: _FakePort, error: Exception, _mp: pytest.MonkeyPatch) -> Any:
    turn = _tools(port, "read_write")
    _call(port, "wiki_read_page", {"path": "S"}, turn)
    port.raise_on_propose_edit = error
    return _call(
        port, "wiki_propose_page_text", {"path": "S", "content_md": "new"}, turn
    )


def _proposing_page(port: _FakePort, error: Exception, mp: pytest.MonkeyPatch) -> Any:
    mp.setattr(port, "propose_page", _failing(error))
    return _call(port, "wiki_propose_page", {"title": "T", "content_md": "x"})


def _reading_status(port: _FakePort, error: Exception, mp: pytest.MonkeyPatch) -> Any:
    mp.setattr(port, "proposal_status", _failing(error))
    return _call(port, "wiki_submit_proposal", {"proposal_id": "prop-2"})


def _reading_back(port: _FakePort, error: Exception, _mp: pytest.MonkeyPatch) -> Any:
    # The read caches the tree, so only the read-back after the status lists.
    turn = _tools(port, "read_write")
    _call(port, "wiki_read_page", {"path": "S"}, turn)
    port.raise_on_list = error
    return _call(port, "wiki_submit_proposal", {"proposal_id": "prop-2"}, turn)


def _searching(port: _FakePort, error: Exception, mp: pytest.MonkeyPatch) -> Any:
    mp.setattr(port, "search", _failing(error))
    return _call(port, "wiki_search", {"query": "support"})


def _search_refresh(port: _FakePort, error: Exception, _mp: pytest.MonkeyPatch) -> Any:
    turn = _tools(port)
    _call(port, "wiki_list_pages", {}, turn)
    port.raise_on_list = error
    return _call(port, "wiki_search", {"query": "support"}, turn)


STOP_SCENARIOS: dict[str, Scenario] = {
    "searching": _searching,
    "search-refresh": _search_refresh,
    "listing": _listing,
    "resolving": _resolving,
    "reading": _reading,
    "proposing-text": _proposing_text,
    "proposing-page": _proposing_page,
    "reading-status": _reading_status,
    "reading-back": _reading_back,
}


@pytest.mark.parametrize("chained", [False, True], ids=["direct", "chained"])
@pytest.mark.parametrize(
    "stop_type",
    [AuthorityLostError, DelegationUnavailableError],
    ids=["authority_lost", "delegation_unavailable"],
)
@pytest.mark.parametrize("scenario", STOP_SCENARIOS)
def test_a_run_stop_escapes_every_tool_path(
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    stop_type: type[RunStopError],
    chained: bool,
) -> None:
    """Text would let the model carry on for a run that lost its authority."""

    port = _FakePort(pages=(_page("s1", "S"),), content="body")
    port.publish_slug = "s1"
    stop = stop_type()

    with pytest.raises(stop_type) as raised:
        STOP_SCENARIOS[scenario](port, _chained(stop) if chained else stop, monkeypatch)

    assert raised.value is stop


@pytest.mark.parametrize("chained", [False, True], ids=["direct", "chained"])
@pytest.mark.parametrize(
    "stop_type",
    [AuthorityLostError, DelegationUnavailableError],
    ids=["authority_lost", "delegation_unavailable"],
)
def test_a_run_stop_escapes_the_prompt_composition(
    stop_type: type[RunStopError], chained: bool
) -> None:
    stop = stop_type()
    port = _FakePort(raises=_chained(stop) if chained else stop)
    middleware = _TeamWikiPromptMiddleware(port, can_write=False)
    request = ModelRequest(model=FakeMessagesListChatModel(responses=[]), messages=[])

    async def _model(_request: ModelRequest) -> ModelResponse:
        raise AssertionError("the model must not be called")

    with pytest.raises(stop_type) as raised:
        asyncio.run(middleware.awrap_model_call(request, _model))

    assert raised.value is stop


def test_a_run_stop_in_prompt_composition_cancels_the_other_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = AuthorityLostError()
    port = _FakePort()
    listing = {"cancelled": False, "finished": False}

    async def read_rules() -> str:
        await asyncio.sleep(0)
        raise stop

    async def list_pages() -> tuple[WikiPageRef, ...]:
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            listing["cancelled"] = True
            raise
        listing["finished"] = True
        return ()

    monkeypatch.setattr(port, "read_rules", read_rules)
    monkeypatch.setattr(port, "list_pages", list_pages)

    async def compose() -> list[asyncio.Task[Any]]:
        with pytest.raises(AuthorityLostError):
            await _TeamWikiPromptMiddleware(port, can_write=False)._compose()
        return [
            task for task in asyncio.all_tasks() if task is not asyncio.current_task()
        ]

    assert asyncio.run(compose()) == []
    assert listing == {"cancelled": True, "finished": False}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("token_status", "wiki_status", "stop_type"),
    [(200, 403, AuthorityLostError), (503, 200, DelegationUnavailableError)],
    ids=["refused", "acquisition-failed"],
)
async def test_the_runtime_adapter_stop_ends_the_tool_call(
    monkeypatch: pytest.MonkeyPatch,
    token_status: int,
    wiki_status: int,
    stop_type: type[RunStopError],
) -> None:
    """The runtime's own adapter over a real delegated provider; only the
    identity provider and the control plane answer locally."""

    monkeypatch.setenv(WORKLOAD_SECRET_ENV, "synthetic")
    tokens = M2MTokenProvider(
        M2MAuthConfig(
            keycloak_realm_url="https://iam.invalid/realms/test",
            client_id="test-workload",
            secret_env=WORKLOAD_SECRET_ENV,
        ),
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                token_status, json={"access_token": "workload", "expires_in": 300}
            )
        ),
    )
    runtime = DelegationRuntime(
        config=DelegationConfig(act_for_people=True), token_provider=tokens
    )
    runtime.records.admit(RunRecord(run_id="run-1", person_id="p-1", agent_id="a-1"))
    binding = BoundRuntimeContext(
        runtime_context=RuntimeContext(
            session_id="s", user_id="p-1", team_id="t-1", space_id="s-1"
        ),
        portable_context=PortableContext(
            request_id="r",
            correlation_id="c",
            actor="p-1",
            tenant="default",
            environment=PortableEnvironment.DEV,
        ),
    )
    received: list[httpx.Request] = []

    def _control_plane(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(wiki_status, text=UPSTREAM_MARKER)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_control_plane)
    ) as client:
        adapter = TeamWikiAdapter(
            binding=binding,
            control_plane_url="http://control-plane.invalid/v1",
            http_client=client,
            credentials=runtime.provider_for(run_id="run-1", agent_id="a-1"),
        )
        tool = _tools(adapter)["wiki_list_pages"]
        with pytest.raises(stop_type) as raised:
            await tool.ainvoke(
                {"type": "tool_call", "name": tool.name, "args": {}, "id": "c1"}
            )

    assert UPSTREAM_MARKER not in str(raised.value)
    assert len(received) == (1 if wiki_status == 403 else 0)


def test_proposal_tools_describe_the_native_format_without_parsing_it() -> None:
    tools = _tools(_FakePort(), "read_write")
    for name in ("wiki_propose_page", "wiki_propose_page_text"):
        description = " ".join(tools[name].description.split())
        assert "explicit native type" in description
        assert (
            "topic, procedure, decision, reference, source, hub or untyped"
            in description
        )
        assert "Preserve existing unknown header fields" in description
        assert "title, generated, verified, status or superseded_by" in description


@pytest.mark.parametrize("mode", ["read", "read_write"])
@pytest.mark.parametrize("filters", [{}, {"type": "procedure", "tag": "support"}])
def test_search_filters_and_server_continuation(
    mode: str, filters: dict[str, str]
) -> None:
    port = _FakePort(pages=(_page("internal-slug", "Help"),))
    port.search_result = WikiSearchResult(
        hits=(
            WikiSearchHit(
                page_id="internal-slug",
                slug="internal-slug",
                title="Help",
                page_type="procedure",
                description="How to help",
                excerpt="A plain excerpt",
            ),
        ),
        next_offset=37,
        truncated=True,
    )
    turn = _tools(port, mode)
    text = _call(
        port, "wiki_search", {"query": "support", "offset": 12, **filters}, turn
    ).content
    assert port.search_calls == [
        ("support", filters.get("type"), filters.get("tag"), 12)
    ]
    assert "- Help | type=procedure | How to help | A plain excerpt" in text
    assert "internal-slug" not in text
    assert "next_offset=37 truncated=true" in text
    assert "refine the query" in text
    assert "limit" not in turn["wiki_search"].args


@pytest.mark.parametrize("change", ["creation", "rename", "move"])
def test_search_refreshes_paths_and_shares_the_tree_with_reads(change: str) -> None:
    port = _FakePort(
        pages=(_page("parent", "Parent"), _page("child", "Old")), content="Answer"
    )
    turn = _tools(port)
    _call(port, "wiki_list_pages", {}, turn)
    target = _page(
        "new" if change == "creation" else "child",
        "New",
        "parent" if change == "move" else None,
    )
    port.set_pages((_page("parent", "Parent"), target))
    port.search_result = WikiSearchResult(
        hits=(
            WikiSearchHit(
                page_id=target.page_id,
                slug=target.slug,
                title="Old search title",
                page_type="topic",
                description=None,
                excerpt="Answer",
            ),
        ),
        next_offset=None,
        truncated=False,
    )
    result = _call(port, "wiki_search", {"query": "answer"}, turn)
    path = "Parent / New" if change == "move" else "New"
    assert f"- {path} | type=topic | Answer" in result.content
    assert "Old search title" not in result.content
    assert port.list_calls == 2
    read = _call(port, "wiki_read_page", {"path": path}, turn)
    assert "Answer" in read.content
    assert port.list_calls == 2


@pytest.mark.parametrize(
    "case",
    ["missing", "recreated", "file", "ambiguous", "parent-missing", "cycle", "depth"],
)
def test_search_omits_unaddressable_hits_without_losing_continuation(case: str) -> None:
    target = _page("target-secret", "Target")
    pages: tuple[WikiPageRef, ...] = ()
    if case == "recreated":
        pages = (
            WikiPageRef(page_id="different-id", slug=target.slug, title=target.title),
        )
    elif case == "file":
        pages = (target.model_copy(update={"kind": "file"}),)
    elif case == "ambiguous":
        target = _page("target-secret", "Parent / Child")
        pages = (target, _page("p", "Parent"), _page("c", "Child", "p"))
    elif case == "parent-missing":
        target = _page("target-secret", "Target", "missing")
        pages = (target,)
    elif case == "cycle":
        target = _page("target-secret", "Target", "other")
        pages = (target, _page("other", "Other", target.slug))
    elif case == "depth":
        ancestors = tuple(
            _page(f"p{i}", f"Level {i}", f"p{i - 1}" if i else None) for i in range(16)
        )
        target = _page("target-secret", "Target", "p15")
        pages = (*ancestors, target)
    port = _FakePort(pages=pages)
    port.search_result = WikiSearchResult(
        hits=(
            WikiSearchHit(
                page_id=target.page_id,
                slug=target.slug,
                title=target.title,
                page_type="topic",
                description=None,
                excerpt="hidden excerpt",
            ),
        ),
        next_offset=19,
        truncated=True,
    )
    text = _call(port, "wiki_search", {"query": "query"}).content
    assert "1 search hit(s) omitted" in text
    assert "next_offset=19 truncated=true" in text
    assert "target-secret" not in text
    assert "hidden excerpt" not in text
    assert not any(line.startswith("- ") for line in text.splitlines())
    assert port.list_calls == 1


def test_search_preserves_authored_identifiers_and_one_line_per_hit() -> None:
    page = _page("slug-secret", "Authored id 123e4567-e89b-12d3-a456-426614174000")
    port = _FakePort(pages=(page,))
    authored = "slug-secret and 123e4567-e89b-12d3-a456-426614174000"
    port.search_result = WikiSearchResult(
        hits=(
            WikiSearchHit(
                page_id=page.page_id,
                slug=page.slug,
                title=page.title,
                page_type="reference",
                description=authored,
                excerpt="é" * 200 + "\n" + authored,
            ),
        ),
        next_offset=None,
        truncated=False,
    )
    text = _call(port, "wiki_search", {"query": "query"}).content
    assert authored in text
    assert "é" * 200 in text
    assert len([line for line in text.splitlines() if line.startswith("- ")]) == 1
    assert "page_id=" not in text and "slug=" not in text


@pytest.mark.parametrize(
    "next_offset, truncated", [(None, False), (20, False), (None, True), (20, True)]
)
def test_empty_search_and_empty_filters(
    next_offset: int | None, truncated: bool
) -> None:
    port = _FakePort()
    port.search_result = WikiSearchResult(
        hits=(), next_offset=next_offset, truncated=truncated
    )
    text = _call(
        port, "wiki_search", {"query": "absent", "type": "", "tag": ""}
    ).content
    assert "No results in this search batch" in text
    assert f"next_offset={next_offset} truncated={str(truncated).lower()}" in text
    assert port.search_calls == [("absent", None, None, 0)]
    assert port.list_calls == 1


@pytest.mark.parametrize("status", [404, 422])
def test_search_refusals_remain_actionable(status: int) -> None:
    result = _call(
        _FakePort(
            raises=TeamWikiPortError("query must not be empty", status_code=status)
        ),
        "wiki_search",
        {"query": ""},
    )
    assert result.artifact.is_error
    assert "query must not be empty" in result.content


def test_search_and_direct_confirmation_guidance() -> None:
    port = _FakePort()
    for can_write in (False, True):
        block = asyncio.run(
            _TeamWikiPromptMiddleware(port, can_write=can_write)._wiki_block()
        )
        assert "Search before you read" in block
        assert "wiki_list_pages browses all pages and files" in block
        if can_write:
            assert "without a prior prose confirmation question" in block
    tools = _tools(port, "read_write")
    for name in (
        "wiki_propose_page",
        "wiki_propose_page_text",
        "wiki_propose_file",
        "wiki_submit_proposal",
    ):
        assert "without a prior prose confirmation" in " ".join(
            tools[name].description.split()
        )
    for name in ("wiki_propose_page", "wiki_propose_page_text"):
        assert "tags: [onboarding, support]" in tools[name].description
    prepared = _call(
        port, "wiki_propose_page", {"title": "Help", "content_md": "body"}, tools
    )
    assert "call wiki_submit_proposal directly" in prepared.content
