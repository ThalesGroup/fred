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
from typing import Any

import pytest
from fred_capability_team_wiki.wiki.capability import (
    PAGE_READ_MAX_CHARS,
    TeamWikiCapability,
    TeamWikiConfig,
    _format_page_batch,
    _TeamWikiPromptMiddleware,
)
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
)
from fred_sdk.contracts.runtime import (
    RuntimeServices,
    TeamWikiPort,
    TeamWikiPortError,
    WikiPageContent,
    WikiPageRef,
    WikiProposalRef,
)


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
        self.list_calls = 0
        self.rules_calls = 0
        self.proposed: list[tuple[str, str]] = []
        self.propose_bases: list[str] = []
        self.published: list[str] = []
        # What the next publish lands as, so a test can publish onto an
        # existing page (an edit) or onto a new one (a creation).
        self.publish_slug = "some-slug"
        self.publish_title = "Some Page"
        # Fails only `list_pages`, so a test can break the tree read back
        # AFTER a write has already landed.
        self.raise_on_list: Exception | None = None

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
        self.proposed.append((slug, content_md))
        self.propose_bases.append(base_revision_id)
        return WikiProposalRef(
            proposal_id="prop-2", title=slug, slug=slug, summary=f"rewrite “{slug}”"
        )

    async def publish_proposal(self, proposal_id: str) -> str:
        if self._raises is not None:
            raise self._raises
        self.published.append(proposal_id)
        # A publish changes the tree, and the tools re-read it to name where
        # the page ended up. A fake that published into nothing would let the
        # "it is still at <path>" wording pass untested.
        if all(page.slug != self.publish_slug for page in self._pages):
            self._pages = (
                *self._pages,
                _page(self.publish_slug, self.publish_title),
            )
        return self.publish_slug


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
    return WikiPageRef(page_id=slug, slug=slug, title=title, parent_slug=parent)


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
    _call(port, "wiki_publish_proposal", {"proposal_id": "prop-1"}, turn)

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

    import fred_capability_team_wiki.wiki.capability as cap_module

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

    assert message.artifact.is_error is True
    assert "not allowed" in message.content
    assert "rules page cannot be changed by an agent" in message.content


def test_an_unknown_path_is_an_error_not_an_empty_page() -> None:
    """Handing back an empty page would have the model report the topic as
    undocumented — a confident answer built on a page that does not exist."""

    port = _FakePort(pages=(_page("s1", "Onboarding"),))
    message = _call(port, "wiki_read_page", {"path": "Ghost"})

    assert message.artifact.is_error is True
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

    assert message.artifact.is_error is True
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
    assert "End of page reached" in second


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

    assert set(_tools(_FakePort())) == {"wiki_list_pages", "wiki_read_page"}


def test_read_write_mode_adds_proposing_and_publishing_only() -> None:
    """And nothing else, ever: no delete, rename or move tool exists here. The
    RFC's §5.4 invariant is an absence, not a check that could be bypassed."""

    names = set(_tools(_FakePort(), "read_write"))

    assert names == {
        "wiki_list_pages",
        "wiki_read_page",
        "wiki_propose_page_text",
        "wiki_propose_page",
        "wiki_publish_proposal",
    }
    assert not any("delete" in n or "rename" in n or "move" in n for n in names)


def test_only_publishing_is_gated_for_approval() -> None:
    """Gating the propose tools would ask the user to approve a draft they
    cannot see yet: the gate runs before the tool and carries only a truncated
    argument preview. The proposal is stored first so the modal has something
    to diff."""

    specs = TeamWikiCapability().hitl_specs()

    assert [s.tool for s in specs] == ["wiki_publish_proposal"]
    assert specs[0].require is True


def test_publishing_an_edit_says_the_page_did_not_move() -> None:
    """Field evidence, 2026-09-07: asked to MOVE two pages, an agent re-proposed
    each page's existing text, published both, and reported the move done — a
    bare "Published" was all it had to go on. The result names what changed."""

    port = _FakePort(pages=(_page("s1", "S"),))
    port.publish_slug = "s1"
    turn = _tools(port, "read_write")
    _call(port, "wiki_read_page", {"path": "S"}, turn)
    _call(port, "wiki_propose_page_text", {"path": "S", "content_md": "new"}, turn)
    message = _call(port, "wiki_publish_proposal", {"proposal_id": "prop-2"}, turn)

    assert "text was replaced" in message.content
    # The page's real path, not a general assurance: a belief that the page
    # moved has to contradict a literal address to survive.
    assert "still at 'S'" in message.content
    assert "never moves a page" in message.content


def test_publishing_a_new_page_says_it_was_created() -> None:
    port = _FakePort(pages=(_page("s1", "S"),))
    port.publish_title = "T"
    turn = _tools(port, "read_write")
    _call(port, "wiki_propose_page", {"title": "T", "content_md": "x"}, turn)
    message = _call(port, "wiki_publish_proposal", {"proposal_id": "prop-1"}, turn)

    assert "created at 'T'" in message.content
    assert "text was replaced" not in message.content


def test_publishing_tells_an_edit_from_a_creation_across_the_approval_gate() -> None:
    """The gate interrupts publishing and the resume arrives as a SEPARATE
    request, which rebuilds the tools closure. Anything the propose call
    remembered there is gone, so the distinction has to come from the wiki —
    otherwise every approved edit is announced as a new page."""

    port = _FakePort(pages=(_page("s1", "S"),))
    port.publish_slug = "s1"

    # Read and propose share one binding; publish gets the resume's fresh
    # closure, same as the gate actually does.
    propose_turn = _tools(port, "read_write")
    _call(port, "wiki_read_page", {"path": "S"}, propose_turn)
    _call(
        port, "wiki_propose_page_text", {"path": "S", "content_md": "new"}, propose_turn
    )
    message = _call(port, "wiki_publish_proposal", {"proposal_id": "prop-2"})

    assert "text was replaced" in message.content
    assert "created" not in message.content


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
    message = _call(port, "wiki_publish_proposal", {"proposal_id": "prop-2"}, turn)

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
    assert "publish the parent" in block


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
    assert "wiki_publish_proposal" in message.content


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


def test_proposing_without_reading_first_is_refused_locally() -> None:
    """A model that never read the page this turn has no revision to anchor
    on. Refusing here — before the port is even called — is what stops a
    proposal being silently created against "whatever is current"."""

    port = _FakePort(pages=(_page("s1", "S"),))
    message = _call(port, "wiki_propose_page_text", {"path": "S", "content_md": "new"})

    assert message.artifact.is_error is True
    assert "wiki_read_page" in message.content
    assert port.proposed == []


def test_publishing_reports_the_review_mark() -> None:
    port = _FakePort()
    message = _call(port, "wiki_publish_proposal", {"proposal_id": "prop-2"})

    assert port.published == ["prop-2"]
    assert "review mark" in message.content


def test_a_stale_proposal_tells_the_model_what_to_do_about_it() -> None:
    """Someone edited the page while the proposal waited. Publishing must not
    overwrite them — and "the wiki could not be reached" would have the model
    retry the same doomed call instead of rebasing its edit."""

    port = _FakePort(raises=TeamWikiPortError("stale", status_code=409))
    message = _call(port, "wiki_publish_proposal", {"proposal_id": "prop-2"})

    assert message.artifact.is_error is True
    assert "changed since you read it" in message.content
    assert "redo your edit" in message.content


def test_the_write_mode_prompt_describes_the_two_steps() -> None:
    port = _FakePort(pages=(_page("a", "A"),))
    block = asyncio.run(_TeamWikiPromptMiddleware(port, can_write=True)._compose())

    assert "wiki_publish_proposal" in block
    assert "replaces it whole" in block
    assert "never change the rules page" in block
    # The read-only wording must NOT survive into write mode: it would tell an
    # agent that can write that it cannot.
    assert "You cannot change it" not in block
