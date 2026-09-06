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
from typing import Any

import pytest
from fred_capability_team_wiki.wiki.capability import (
    PAGE_READ_MAX_CHARS,
    TeamWikiCapability,
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
)


class _FakePort(TeamWikiPort):
    def __init__(
        self,
        *,
        pages: tuple[WikiPageRef, ...] = (),
        content: str = "",
        rules: str = "",
        raises: Exception | None = None,
    ) -> None:
        self._pages = pages
        self._content = content
        self._rules = rules
        self._raises = raises
        self.list_calls = 0
        self.rules_calls = 0

    async def list_pages(self) -> tuple[WikiPageRef, ...]:
        self.list_calls += 1
        if self._raises is not None:
            raise self._raises
        return self._pages

    async def read_page(self, slug: str, *, max_chars: int = 8_000) -> WikiPageContent:
        if self._raises is not None:
            raise self._raises
        truncated = len(self._content) > max_chars
        return WikiPageContent(
            slug=slug,
            title=slug.title(),
            content_md=self._content[:max_chars] if truncated else self._content,
            truncated=truncated,
        )

    async def read_rules(self) -> str:
        self.rules_calls += 1
        if self._raises is not None:
            raise self._raises
        return self._rules


def _ctx(port: TeamWikiPort | None) -> Any:
    return CapabilityContext(
        identity=CapabilityIdentity(user_id="u", session_id="s"),
        config=EmptyModel(),
        turn_options=EmptyModel(),
        services=RuntimeServices(team_wiki=port),
    )


def _tools(port: TeamWikiPort | None) -> dict[str, Any]:
    return {t.name: t for t in TeamWikiCapability().tools(_ctx(port))}


def _call(port: TeamWikiPort | None, name: str, args: dict[str, Any]) -> Any:
    """Invoke through a ToolCall, so a `content_and_artifact` tool hands back
    the ToolMessage the runtime actually sees (content + artifact), not the
    raw tuple."""

    the_tool = _tools(port)[name]
    return asyncio.run(
        the_tool.ainvoke({"type": "tool_call", "name": name, "args": args, "id": "c1"})
    )


def _page(slug: str, title: str, parent: str | None = None) -> WikiPageRef:
    return WikiPageRef(page_id=slug, slug=slug, title=title, parent_slug=parent)


def test_index_shows_the_hierarchy_and_the_slug_to_call_back_with() -> None:
    port = _FakePort(
        pages=(
            _page("onboarding", "Onboarding"),
            _page("tooling", "Tooling", parent="onboarding"),
        )
    )
    text = _call(port, "wiki_list_pages", {}).content

    assert "- Onboarding — onboarding" in text
    # Indented under its parent: an index that flattens the tree describes a
    # different wiki than the one the team sees.
    assert "  - Tooling — tooling" in text


def test_an_empty_wiki_says_so_rather_than_returning_nothing() -> None:
    text = _call(_FakePort(), "wiki_list_pages", {}).content

    assert "no pages yet" in text


def test_a_refused_read_names_the_cause_and_is_an_error_result() -> None:
    """A disabled capability is the commonest cause. The model must be told it
    cannot read the wiki AT ALL this turn, or it retries the call until the
    step budget runs out."""

    port = _FakePort(raises=TeamWikiPortError("nope", status_code=403))
    message = _call(port, "wiki_read_page", {"slug": "x"})

    assert message.artifact.is_error is True
    assert "not available to you" in message.content


def test_an_unknown_slug_is_an_error_not_an_empty_page() -> None:
    """Handing back an empty page would have the model report the topic as
    undocumented — a confident answer built on a page that does not exist."""

    port = _FakePort(raises=TeamWikiPortError("gone", status_code=404))
    message = _call(port, "wiki_read_page", {"slug": "ghost"})

    assert message.artifact.is_error is True
    assert "no such wiki page" in message.content


def test_a_long_page_comes_back_cut_and_says_so() -> None:
    port = _FakePort(content="x" * (PAGE_READ_MAX_CHARS + 500))
    message = _call(port, "wiki_read_page", {"slug": "big"})

    assert message.artifact.is_error is False
    assert "longer than what you were given" in message.content


def test_a_missing_port_fails_loud() -> None:
    """A bare harness must not look like an empty wiki."""

    with pytest.raises(RuntimeError):
        _call(None, "wiki_list_pages", {})


def test_the_prompt_block_carries_the_rules_and_the_index() -> None:
    port = _FakePort(pages=(_page("onboarding", "Onboarding"),), rules="Never guess.")
    block = asyncio.run(_TeamWikiPromptMiddleware(port)._compose())

    assert "Never guess." in block
    assert "- Onboarding — onboarding" in block
    assert "never act against them" in block


def test_the_prompt_block_is_fetched_once_per_turn() -> None:
    """A ReAct turn calls the model once per tool round. Re-reading the wiki on
    each would put two control-plane round-trips on the latency path of every
    round, to fetch text that cannot have changed."""

    port = _FakePort(pages=(_page("a", "A"),), rules="r")
    middleware = _TeamWikiPromptMiddleware(port)

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
    block = asyncio.run(_TeamWikiPromptMiddleware(port)._compose())

    assert "could not be read this turn" in block
    assert "Do not state or imply what it contains" in block
