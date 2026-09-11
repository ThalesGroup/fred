from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, cast

import pytest
from control_plane_backend.models.team_wiki_models import (
    MAX_REVISION_PAGE_SIZE,
    RULES_PAGE_SLUG,
)
from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.team_wiki import service as wiki_service
from control_plane_backend.team_wiki.schemas import (
    CreateWikiPageRequest,
    ProposeEditRequest,
    ProposePageRequest,
    SetNeedsReviewRequest,
    UpdateWikiPageContentRequest,
    UpdateWikiPageMetadataRequest,
    UpdateWikiRulesRequest,
)
from control_plane_backend.team_wiki.service import (
    WIKI_READ_PERMISSION,
    WIKI_WRITE_PERMISSION,
    WikiRequestError,
    _unique_slug,
)
from control_plane_backend.team_wiki.store import (
    RevisionCursor,
    WikiPageDepthExceededError,
    WikiPageInvalidMoveError,
    WikiPageNotFoundError,
    WikiPageRecord,
    WikiPageRulesParentError,
    WikiProposalNoLongerPendingError,
    WikiRevisionConflictError,
    WikiRevisionRecord,
    _StaleBaseWrite,
)
from fred_core import KeycloakUser
from fred_core.common import TeamId
from pydantic import ValidationError

TEAM = TeamId("team-a")


# ── pure helpers ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_slug_says_nothing_about_the_title_it_was_minted_for() -> None:
    """A rename never changes the slug — it is the URL, and nothing maps an old
    one to a page. A slug derived from the first title therefore outlives it:
    "Les Shinigamis" kept the URL `sous-page-11`, and a model handed that pair
    read it as one name and called back with a slug that did not exist."""

    store = cast(Any, _Store())
    slug = await _unique_slug(store, TEAM)

    assert "shinigami" not in slug
    assert slug.isalnum() and len(slug) == 8


@pytest.mark.asyncio
async def test_a_slug_never_collides_with_one_the_team_already_has() -> None:
    store = cast(Any, _Store())
    slugs = {await _unique_slug(store, TEAM) for _ in range(50)}

    assert len(slugs) == 50


def _page(
    page_id: str,
    parent: str | None,
    *,
    kind: str = "page",
    slug: str | None = None,
) -> WikiPageRecord:
    return WikiPageRecord(
        page_id=page_id,
        team_id=TEAM,
        slug=slug or page_id,
        title=page_id,
        kind=kind,
        parent_page_id=parent,
        current_revision_id=f"rev-{page_id}",
    )


def _revision(
    revision_id: str,
    page_id: str,
    *,
    status: str = "published",
    created_at: datetime | None = None,
) -> WikiRevisionRecord:
    return WikiRevisionRecord(
        revision_id=revision_id,
        page_id=page_id,
        team_id=TEAM,
        content_md="body",
        status=status,
        created_at=created_at,
    )


# `_child_depth_under`, `_subtree_height` and `_is_descendant` moved to
# `store.py` along with the structural validation they back — covered in
# `test_team_wiki_store.py` now, against the real store under its lock.


# ── sibling titles ───────────────────────────────────────────────────────────


def _titled(page_id: str, title: str, parent: str | None = None) -> WikiPageRecord:
    page = _page(page_id, parent)
    page.title = title
    return page


@pytest.mark.asyncio
async def test_two_pages_under_one_parent_cannot_share_a_title(
    gate: _RecordingGate,
) -> None:
    """An agent addresses a page by its path — its titles from the root — so
    two namesakes under one parent would give two pages the same address."""

    store = _Store()
    store.pages.append(_titled("p1", "Espagne"))

    with pytest.raises(wiki_service.WikiRequestError) as refused:
        await wiki_service.create_wiki_page(
            _user(), TEAM, CreateWikiPageRequest(title="  espagne "), _deps(store)
        )

    assert refused.value.http_status == 409


@pytest.mark.asyncio
async def test_the_same_title_is_free_under_a_different_parent(
    gate: _RecordingGate,
) -> None:
    """The rule is about siblings, not the whole wiki: "Espagne" under Ventes
    and under Achats are two different addresses."""

    store = _Store()
    store.pages.append(_titled("ventes", "Ventes"))
    store.pages.append(_titled("achats", "Achats"))
    store.pages.append(_titled("p1", "Espagne", parent="ventes"))

    await wiki_service.create_wiki_page(
        _user(),
        TEAM,
        CreateWikiPageRequest(title="Espagne", parent_page_id="achats"),
        _deps(store),
    )


@pytest.mark.asyncio
async def test_a_rename_onto_a_sibling_title_is_refused(gate: _RecordingGate) -> None:
    store = _Store()
    store.pages.append(_titled("p1", "Espagne"))
    store.pages.append(_titled("p2", "Italie"))

    with pytest.raises(wiki_service.WikiRequestError) as refused:
        await wiki_service.update_wiki_page_metadata(
            _user(),
            TEAM,
            "p2",
            UpdateWikiPageMetadataRequest(title="Espagne"),
            _deps(store),
        )

    assert refused.value.http_status == 409


@pytest.mark.asyncio
async def test_renaming_a_page_to_its_own_title_is_not_a_collision(
    gate: _RecordingGate,
) -> None:
    """The page must not be compared against itself, or saving a page without
    touching its title would refuse."""

    store = _Store()
    store.pages.append(_titled("p1", "Espagne"))

    await wiki_service.update_wiki_page_metadata(
        _user(),
        TEAM,
        "p1",
        UpdateWikiPageMetadataRequest(title="Espagne"),
        _deps(store),
    )


@pytest.mark.asyncio
async def test_a_move_next_to_a_namesake_is_refused(gate: _RecordingGate) -> None:
    """A move carries the title with it, so it is checked against where the
    page is going, not where it is."""

    store = _Store()
    store.pages.append(_titled("ventes", "Ventes"))
    store.pages.append(_titled("p1", "Espagne", parent="ventes"))
    store.pages.append(_titled("p2", "Espagne"))

    with pytest.raises(wiki_service.WikiRequestError) as refused:
        await wiki_service.update_wiki_page_metadata(
            _user(),
            TEAM,
            "p2",
            UpdateWikiPageMetadataRequest(parent_page_id="ventes"),
            _deps(store),
        )

    assert refused.value.http_status == 409


@pytest.mark.asyncio
async def test_a_proposal_that_changes_nothing_is_refused(gate: _RecordingGate) -> None:
    """Field evidence, 2026-09-07: asked to MOVE two pages, an agent used the
    only write tool it had and re-proposed each page's existing text
    byte-for-byte. Both published, both changed nothing, and the agent read
    "published" as "moved" — then reported a hierarchy that did not exist."""

    store = _Store()
    page = _titled("p1", "Espagne")
    store.pages.append(page)
    store.revisions["rev-p1"] = _revision("rev-p1", "p1")

    with pytest.raises(wiki_service.WikiRequestError) as refused:
        await wiki_service.propose_wiki_edit(
            _user(),
            TEAM,
            ProposeEditRequest(slug="p1", content_md="body", base_revision_id="rev-p1"),
            _deps(store),
        )

    assert refused.value.http_status == 409
    assert "cannot be moved" in str(refused.value)
    assert store.proposals == []


# ── authorization gates ──────────────────────────────────────────────────────


class _RecordingGate:
    """Stands in for `require_team_access`, recording what each call demanded."""

    def __init__(self) -> None:
        self.permissions: list[Any] = []

    async def __call__(
        self, _user: Any, team_id: TeamId, _deps: Any, permissions: Any = None
    ) -> TeamId:
        self.permissions.append(permissions)
        return team_id


class _User:
    uid = "alice"


class _Store:
    """Enough store for the service tests. Most writes are refused before they
    reach it; the two that are meant to succeed record what they were given."""

    def __init__(self) -> None:
        self.pages: list[WikiPageRecord] = []
        self.revisions: dict[str, WikiRevisionRecord] = {}
        self.proposals: list[WikiRevisionRecord] = []
        # The structural checks these two calls guard (parent existence, kind,
        # depth, cycle) now run inside the real store's locked transaction —
        # this fake has no tree to validate against, so a test that wants to
        # see the service translate one of those failures sets the exception
        # to raise here instead of re-implementing the check.
        self.raise_from_create_page: Exception | None = None
        self.raise_from_update_page_metadata: Exception | None = None
        self.raise_from_publish_proposal: Exception | None = None
        self.raise_from_set_needs_review: Exception | None = None
        self.set_needs_review_calls: list[dict[str, Any]] = []

    async def list_pages(self, _team_id: TeamId) -> list[WikiPageRecord]:
        return self.pages

    async def get_page(self, _team_id: TeamId, page_id: str) -> WikiPageRecord | None:
        return next((p for p in self.pages if p.page_id == page_id), None)

    async def get_page_by_slug(
        self, _team_id: TeamId, slug: str
    ) -> WikiPageRecord | None:
        return next((p for p in self.pages if p.slug == slug), None)

    async def get_revision(
        self, _team_id: TeamId, revision_id: str
    ) -> WikiRevisionRecord | None:
        return self.revisions.get(revision_id)

    async def list_revisions(
        self,
        _team_id: TeamId,
        page_id: str,
        *,
        limit: int,
        before: RevisionCursor | None = None,
    ) -> list[WikiRevisionRecord]:
        """Mirrors the real store's SQL enough for the service's own cursor
        arithmetic (the `limit + 1` trick, `next_cursor` from the last
        RETURNED row) to be tested without a database: same filter, same
        `(created_at, revision_id)` descending order, same keyset condition.
        """

        matches = [
            r
            for r in self.revisions.values()
            if r.page_id == page_id and r.status not in ("proposed", "rejected")
        ]
        matches.sort(key=lambda r: (r.created_at, r.revision_id), reverse=True)
        if before is not None:
            matches = [
                r
                for r in matches
                if (r.created_at, r.revision_id)
                < (before.created_at, before.revision_id)
            ]
        return matches[:limit]

    async def create_page(self, **kwargs: Any) -> Any:
        if self.raise_from_create_page is not None:
            raise self.raise_from_create_page
        page = WikiPageRecord(
            page_id=kwargs["slug"],
            team_id=TEAM,
            slug=kwargs["slug"],
            title=kwargs["title"],
            parent_page_id=kwargs.get("parent_page_id"),
            current_revision_id="rev-1",
        )
        self.pages.append(page)
        return SimpleNamespace(page=page, revision=_revision("rev-1", page.page_id))

    async def update_page_metadata(self, **kwargs: Any) -> WikiPageRecord:
        if self.raise_from_update_page_metadata is not None:
            raise self.raise_from_update_page_metadata
        page = next(p for p in self.pages if p.page_id == kwargs["page_id"])
        if kwargs.get("title") is not None:
            page.title = kwargs["title"]
        return page

    async def set_needs_review(self, **kwargs: Any) -> WikiPageRecord:
        self.set_needs_review_calls.append(kwargs)
        if self.raise_from_set_needs_review is not None:
            raise self.raise_from_set_needs_review
        page = next(p for p in self.pages if p.page_id == kwargs["page_id"])
        page.needs_review = kwargs["needs_review"]
        return page

    async def get_proposal(
        self, _team_id: TeamId, proposal_id: str
    ) -> WikiRevisionRecord | None:
        return next((p for p in self.proposals if p.revision_id == proposal_id), None)

    async def publish_proposal(self, **_kwargs: Any) -> WikiPageRecord:
        if self.raise_from_publish_proposal is not None:
            raise self.raise_from_publish_proposal
        raise AssertionError("not needed by the tests that use this fake")

    async def create_proposal(self, **kwargs: Any) -> WikiRevisionRecord:
        record = WikiRevisionRecord(
            revision_id=f"prop-{len(self.proposals) + 1}",
            page_id=kwargs["page_id"] or "new-page",
            team_id=TEAM,
            content_md=kwargs["content_md"],
            status="proposed",
            base_revision_id=kwargs["base_revision_id"],
            proposed_title=kwargs["proposed_title"],
            proposed_parent_page_id=kwargs["proposed_parent_page_id"],
        )
        self.proposals.append(record)
        return record


class _TeamDeps:
    """`rebac` is what the capability gate reads; nothing here queries it —
    `can_team_use_capability` is stubbed per test."""

    rebac = object()


class _Deps:
    team_dependencies = _TeamDeps()

    def __init__(self, store: _Store) -> None:
        self._store = store

    def get_team_wiki_store(self) -> Any:
        return self._store


def _deps(store: _Store) -> ProductServiceDependencies:
    """The fake, as the service's signature wants it.

    Deliberately partial: it implements exactly what the wiki service touches,
    and one cast in one place is what keeps the file type-checkable — a
    per-call-site ignore comment neither documents that nor satisfies the
    checker.
    """

    return cast(ProductServiceDependencies, _Deps(store))


def _user() -> KeycloakUser:
    return cast(KeycloakUser, _User())


@pytest.fixture(autouse=True)
def wiki_capability_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test below is about the wiki's own rules, so the capability gate
    is open. Its own behaviour is covered by the two tests at the bottom of
    this file."""

    async def _enabled(*_args: Any, **_kwargs: Any) -> bool:
        return True

    monkeypatch.setattr(wiki_service, "can_team_use_capability", _enabled)


@pytest.fixture()
def gate(monkeypatch: pytest.MonkeyPatch) -> _RecordingGate:
    recorder = _RecordingGate()
    monkeypatch.setattr(wiki_service, "require_team_access", recorder)
    return recorder


@pytest.mark.asyncio
async def test_reads_demand_a_member_only_permission(gate: _RecordingGate) -> None:
    """`CAN_READ` would admit non-members of a PUBLIC team; the wiki holds a
    team's internal knowledge, so the read gate must be member-only."""

    deps = _deps(_Store())
    await wiki_service.get_wiki_tree(_user(), TEAM, deps)
    assert gate.permissions == [[WIKI_READ_PERMISSION]]
    assert WIKI_READ_PERMISSION.value == "can_read_members"


@pytest.mark.asyncio
async def test_every_write_demands_the_editor_permission(gate: _RecordingGate) -> None:
    """One test over all of them: a write path that forgets its gate is the
    failure this covers, and it is easiest to miss on the least-used route."""

    store = _Store()
    store.pages.append(_page("p1", None))
    deps = _deps(store)
    user = _user()

    # Each call only has to get PAST its gate; whether the partial fake can
    # then carry the write out is not what is under test, so a failure after
    # that point is ignored rather than asserted on.
    async def reached(call: Any) -> None:
        try:
            await call
        except Exception:
            pass  # only the gate matters here, see comment above

    await reached(
        wiki_service.create_wiki_page(
            user, TEAM, CreateWikiPageRequest(title="T"), deps
        )
    )
    await reached(
        wiki_service.update_wiki_page_content(
            user, TEAM, "p1", UpdateWikiPageContentRequest(content_md="x"), deps
        )
    )
    await reached(
        wiki_service.update_wiki_page_metadata(
            user, TEAM, "p1", UpdateWikiPageMetadataRequest(title="T2"), deps
        )
    )
    await reached(
        wiki_service.update_wiki_rules(
            user, TEAM, UpdateWikiRulesRequest(content_md="x"), deps
        )
    )
    await reached(
        wiki_service.set_wiki_page_needs_review(
            user,
            TEAM,
            "p1",
            SetNeedsReviewRequest(needs_review=False, base_revision_id="rev-p1"),
            deps,
        )
    )
    await reached(wiki_service.delete_wiki_page(user, TEAM, "p1", deps))
    await reached(wiki_service.restore_wiki_revision(user, TEAM, "p1", "r1", deps))

    assert gate.permissions == [[WIKI_WRITE_PERMISSION]] * 7
    assert WIKI_WRITE_PERMISSION.value == "can_update_resources"


# ── the rules page cannot be reached through the ordinary page routes ────────


@pytest.mark.asyncio
async def test_the_rules_page_is_not_editable_deletable_or_movable_as_a_page(
    gate: _RecordingGate,
) -> None:
    """The rules page steers every agent holding the capability. It is reachable
    only through its own endpoint — the ordinary page routes refuse it, so a
    caller cannot rewrite the rules by addressing them as an ordinary page."""

    store = _Store()
    rules = WikiPageRecord(
        page_id="rules-1",
        team_id=TEAM,
        slug=RULES_PAGE_SLUG,
        title="Rules",
        kind="rules",
    )
    store.pages.append(rules)
    deps = _deps(store)
    user = _user()

    with pytest.raises(WikiRequestError) as edit:
        await wiki_service.update_wiki_page_content(
            user,
            TEAM,
            "rules-1",
            UpdateWikiPageContentRequest(content_md="hacked"),
            deps,
        )
    assert edit.value.http_status == 400

    with pytest.raises(WikiRequestError) as move:
        await wiki_service.update_wiki_page_metadata(
            user,
            TEAM,
            "rules-1",
            UpdateWikiPageMetadataRequest(title="Not rules"),
            deps,
        )
    assert move.value.http_status == 400

    with pytest.raises(WikiRequestError) as removed:
        await wiki_service.delete_wiki_page(user, TEAM, "rules-1", deps)
    assert removed.value.http_status == 400


# The cycle, depth, parent-existence and rules-parent checks a move or a
# create can fail now run inside the store's structural lock (real-tree
# behaviour covered in `test_team_wiki_store.py`, against the real store).
# What is left to prove here is that the service translates each of the
# store's structural exceptions into the right `WikiRequestError` — so these
# tests inject the exception the real store would raise, rather than
# re-implementing the tree checks in the fake.


@pytest.mark.asyncio
async def test_an_invalid_move_from_the_store_becomes_a_400(
    gate: _RecordingGate,
) -> None:
    store = _Store()
    store.pages.append(_page("p", None))
    store.raise_from_update_page_metadata = WikiPageInvalidMoveError("p")
    deps = _deps(store)

    with pytest.raises(WikiRequestError) as caught:
        await wiki_service.update_wiki_page_metadata(
            _user(), TEAM, "p", UpdateWikiPageMetadataRequest(parent_page_id="p"), deps
        )
    assert caught.value.http_status == 400
    assert "descendant" in str(caught.value)


@pytest.mark.asyncio
async def test_a_depth_exceeded_move_from_the_store_becomes_a_400(
    gate: _RecordingGate,
) -> None:
    store = _Store()
    store.pages.extend([_page("a", None), _page("dest", None)])
    store.raise_from_update_page_metadata = WikiPageDepthExceededError("dest")
    deps = _deps(store)

    with pytest.raises(WikiRequestError) as caught:
        await wiki_service.update_wiki_page_metadata(
            _user(),
            TEAM,
            "a",
            UpdateWikiPageMetadataRequest(parent_page_id="dest"),
            deps,
        )
    assert caught.value.http_status == 400
    assert "deeper" in str(caught.value)


@pytest.mark.asyncio
async def test_a_move_under_a_since_deleted_parent_becomes_a_404(
    gate: _RecordingGate,
) -> None:
    """The parent looked present in the service's own snapshot; the store's
    fresh, lock-protected read is what actually decides."""

    store = _Store()
    store.pages.append(_page("p", None))
    store.raise_from_update_page_metadata = WikiPageNotFoundError("gone-parent")
    deps = _deps(store)

    with pytest.raises(WikiRequestError) as caught:
        await wiki_service.update_wiki_page_metadata(
            _user(),
            TEAM,
            "p",
            UpdateWikiPageMetadataRequest(parent_page_id="gone-parent"),
            deps,
        )
    assert caught.value.http_status == 404
    assert "parent" in str(caught.value)


@pytest.mark.asyncio
async def test_a_move_under_the_rules_page_from_the_store_becomes_a_400(
    gate: _RecordingGate,
) -> None:
    store = _Store()
    store.pages.append(_page("p", None))
    store.raise_from_update_page_metadata = WikiPageRulesParentError("rules-1")
    deps = _deps(store)

    with pytest.raises(WikiRequestError) as caught:
        await wiki_service.update_wiki_page_metadata(
            _user(),
            TEAM,
            "p",
            UpdateWikiPageMetadataRequest(parent_page_id="rules-1"),
            deps,
        )
    assert caught.value.http_status == 400
    assert "have children" in str(caught.value)


@pytest.mark.asyncio
async def test_a_create_under_a_since_deleted_parent_becomes_a_404(
    gate: _RecordingGate,
) -> None:
    store = _Store()
    store.raise_from_create_page = WikiPageNotFoundError("gone-parent")
    deps = _deps(store)

    with pytest.raises(WikiRequestError) as caught:
        await wiki_service.create_wiki_page(
            _user(),
            TEAM,
            CreateWikiPageRequest(title="New", parent_page_id="gone-parent"),
            deps,
        )
    assert caught.value.http_status == 404


@pytest.mark.asyncio
async def test_a_create_past_the_depth_cap_from_the_store_becomes_a_400(
    gate: _RecordingGate,
) -> None:
    store = _Store()
    store.raise_from_create_page = WikiPageDepthExceededError("deep-parent")
    deps = _deps(store)

    with pytest.raises(WikiRequestError) as caught:
        await wiki_service.create_wiki_page(
            _user(),
            TEAM,
            CreateWikiPageRequest(title="New", parent_page_id="deep-parent"),
            deps,
        )
    assert caught.value.http_status == 400
    assert "deeper" in str(caught.value)


@pytest.mark.asyncio
async def test_reading_the_rules_page_never_creates_it(gate: _RecordingGate) -> None:
    """The read gate is member-only. If the read materialised the row, any
    member could create the page that steers every agent's system prompt, and
    be recorded as its author."""

    class _NoWriteStore(_Store):
        async def create_page(self, **_kwargs: Any) -> None:
            raise AssertionError("a read must not write")

    deps = _deps(_NoWriteStore())
    detail = await wiki_service.get_wiki_rules(_user(), TEAM, deps)
    assert detail.content_md == ""
    assert detail.revision_id is None
    assert detail.page.kind == "rules"
    assert gate.permissions == [[WIKI_READ_PERMISSION]]


# ---------------------------------------------------------------------------
# The capability gate (WIKI-03)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_team_without_the_capability_has_no_wiki(
    monkeypatch: pytest.MonkeyPatch, gate: _RecordingGate
) -> None:
    """An admin turning the `team_wiki` capability off takes the wiki away from
    the team's people as well as its agents. 404, not 403: to that team, this
    wiki does not exist."""

    async def _disabled(*_args: Any, **_kwargs: Any) -> bool:
        return False

    monkeypatch.setattr(wiki_service, "can_team_use_capability", _disabled)

    with pytest.raises(wiki_service.WikiRequestError) as caught:
        await wiki_service.get_wiki_tree(_user(), TEAM, _deps(_Store()))
    assert caught.value.http_status == 404


@pytest.mark.asyncio
async def test_the_gate_runs_on_every_entry_point(
    monkeypatch: pytest.MonkeyPatch, gate: _RecordingGate
) -> None:
    """One test over all of them, like the write-permission one above: a route
    added later that reaches the store without the gate is the failure this
    covers, and the read routes are the easiest place to miss it."""

    async def _disabled(*_args: Any, **_kwargs: Any) -> bool:
        return False

    monkeypatch.setattr(wiki_service, "can_team_use_capability", _disabled)
    store = _Store()
    store.pages.append(_page("p1", None))
    deps = _deps(store)
    user = _user()

    calls = [
        wiki_service.get_wiki_tree(user, TEAM, deps),
        wiki_service.get_wiki_page(user, TEAM, "p1", deps),
        wiki_service.get_wiki_rules(user, TEAM, deps),
        wiki_service.list_wiki_revisions(user, TEAM, "p1", deps),
        wiki_service.create_wiki_page(
            user, TEAM, CreateWikiPageRequest(title="T"), deps
        ),
        wiki_service.delete_wiki_page(user, TEAM, "p1", deps),
    ]
    for call in calls:
        with pytest.raises(wiki_service.WikiRequestError) as caught:
            await call
        assert caught.value.http_status == 404


@pytest.mark.asyncio
async def test_availability_answers_no_instead_of_refusing(
    monkeypatch: pytest.MonkeyPatch, gate: _RecordingGate
) -> None:
    """The one route that must NOT 404 when the capability is off — the
    navigation panel asks it precisely to find out."""

    async def _disabled(*_args: Any, **_kwargs: Any) -> bool:
        return False

    monkeypatch.setattr(wiki_service, "can_team_use_capability", _disabled)

    result = await wiki_service.get_wiki_availability(_user(), TEAM, _deps(_Store()))
    assert result.enabled is False


# ---------------------------------------------------------------------------
# Agent proposals (WIKI-04)
#
# The whole point of the two-step write is that nothing reaches the wiki until
# a person says so. These cover what a proposal must NOT be able to do.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_agent_can_never_propose_an_edit_to_the_rules_page(
    gate: _RecordingGate,
) -> None:
    """The rules page steers every agent holding this capability. If an agent
    could rewrite it, the page would protect nothing — §8.6 makes this the one
    kind of page no configuration can reach."""

    store = _Store()
    store.pages.append(_page("rules-page", None, kind="rules", slug="__rules__"))
    deps = _deps(store)

    with pytest.raises(wiki_service.WikiRequestError) as caught:
        await wiki_service.propose_wiki_edit(
            _user(),
            TEAM,
            ProposeEditRequest(
                slug="__rules__", content_md="anything", base_revision_id="whatever"
            ),
            deps,
        )
    assert caught.value.http_status == 403


@pytest.mark.asyncio
async def test_proposing_writes_nothing_to_the_page(gate: _RecordingGate) -> None:
    """A proposal is a suggestion. The page it targets must be untouched until
    someone publishes it — that is what makes the approval real."""

    store = _Store()
    page = _page("p1", None, slug="notes")
    store.pages.append(page)
    deps = _deps(store)

    result = await wiki_service.propose_wiki_edit(
        _user(),
        TEAM,
        ProposeEditRequest(
            slug="notes", content_md="new text", base_revision_id="rev-p1"
        ),
        deps,
    )

    assert result.kind == "edit"
    assert store.proposals[0].status == "proposed"
    assert store.proposals[0].base_revision_id == "rev-p1"
    assert page.current_revision_id == "rev-p1"


@pytest.mark.asyncio
async def test_a_proposal_from_a_stale_read_is_refused(gate: _RecordingGate) -> None:
    """The bug this correction fixes: an agent reads revision A, another
    writer publishes B, and the agent's proposal must not be silently rebased
    onto B — it must be refused so the agent knows to reread."""

    store = _Store()
    page = _page("p1", None, slug="notes")
    page.current_revision_id = "rev-B"
    store.pages.append(page)
    store.revisions["rev-B"] = _revision("rev-B", "p1")

    with pytest.raises(wiki_service.WikiConflictError) as caught:
        await wiki_service.propose_wiki_edit(
            _user(),
            TEAM,
            ProposeEditRequest(
                slug="notes", content_md="edited from A", base_revision_id="rev-A"
            ),
            _deps(store),
        )

    assert caught.value.current_revision_id == "rev-B"
    assert store.proposals == []


@pytest.mark.asyncio
async def test_publish_stale_write_reports_404_when_the_page_is_gone(
    gate: _RecordingGate,
) -> None:
    """The store's compare-and-swap can fail because the page moved on, or
    because it was deleted in the gap before this re-read — those are not the
    same refusal. A deleted page must not come back as a 409 conflict with a
    fabricated empty revision to rebase onto."""

    store = _Store()
    store.proposals.append(
        _revision("prop-1", "p1", status="proposed", created_at=datetime.now())
    )
    store.raise_from_publish_proposal = _StaleBaseWrite()
    # No page in store.pages: get_page(..., "p1") returns None, the same as a
    # page deleted after the store's own CAS already found it stale.

    with pytest.raises(WikiRequestError) as caught:
        await wiki_service.publish_wiki_proposal(_user(), TEAM, "prop-1", _deps(store))

    assert caught.value.http_status == 404


@pytest.mark.asyncio
async def test_publish_reports_the_same_404_when_a_reject_wins_the_race(
    gate: _RecordingGate,
) -> None:
    """The store's CAS on the proposal's own status can fail because a
    decline, the retention sweep, or a session erasure committed between this
    call's lookup and its write — that must read to the caller exactly like
    finding the proposal already rejected, not as a page conflict."""

    store = _Store()
    store.pages.append(_page("p1", None, slug="notes"))
    store.proposals.append(
        _revision("prop-1", "p1", status="proposed", created_at=datetime.now())
    )
    store.raise_from_publish_proposal = WikiProposalNoLongerPendingError("prop-1")

    with pytest.raises(WikiRequestError) as caught:
        await wiki_service.publish_wiki_proposal(_user(), TEAM, "prop-1", _deps(store))

    assert caught.value.http_status == 404
    assert str(caught.value) == "This proposal is no longer pending."


@pytest.mark.asyncio
async def test_a_proposal_cannot_bind_to_another_page_s_revision(
    gate: _RecordingGate,
) -> None:
    """`base_revision_id` is only ever compared against THIS page's current
    revision, so a caller cannot anchor a proposal to a revision id it read
    off a different page (or a different team's page reusing the same id)."""

    store = _Store()
    store.pages.append(_page("p1", None, slug="notes"))
    store.pages.append(_page("p2", None, slug="other"))

    with pytest.raises(wiki_service.WikiConflictError):
        await wiki_service.propose_wiki_edit(
            _user(),
            TEAM,
            ProposeEditRequest(slug="notes", content_md="x", base_revision_id="rev-p2"),
            _deps(store),
        )

    assert store.proposals == []


@pytest.mark.asyncio
async def test_reviewing_threads_the_displayed_revision_to_the_store(
    gate: _RecordingGate,
) -> None:
    """B1: the revision the reviewer displayed must reach the store call
    verbatim — nothing in the service may recompute it from "whatever is
    current now"."""

    store = _Store()
    store.pages.append(_page("p1", None, slug="notes"))

    await wiki_service.set_wiki_page_needs_review(
        _user(),
        TEAM,
        "p1",
        SetNeedsReviewRequest(needs_review=False, base_revision_id="rev-A"),
        _deps(store),
    )

    assert store.set_needs_review_calls[0]["base_revision_id"] == "rev-A"


@pytest.mark.asyncio
async def test_a_review_against_a_superseded_revision_is_refused(
    gate: _RecordingGate,
) -> None:
    """B1: the store's compare-and-swap detected the page moved on since the
    reviewer's read. The service must surface this as the same 409 conflict
    shape every other stale wiki write uses, not let it escape untranslated."""

    store = _Store()
    store.pages.append(_page("p1", None, slug="notes"))
    store.raise_from_set_needs_review = WikiRevisionConflictError("rev-B", "B")

    with pytest.raises(wiki_service.WikiConflictError) as caught:
        await wiki_service.set_wiki_page_needs_review(
            _user(),
            TEAM,
            "p1",
            SetNeedsReviewRequest(needs_review=False, base_revision_id="rev-A"),
            _deps(store),
        )

    assert caught.value.current_revision_id == "rev-B"


@pytest.mark.asyncio
async def test_omitting_the_base_is_a_validation_error_not_an_overwrite(
    gate: _RecordingGate,
) -> None:
    """There is no implicit "use whatever is current" default — the field is
    required, so a caller that forgot to read first fails before the service
    is even reached."""

    with pytest.raises(ValidationError):
        ProposeEditRequest(slug="notes", content_md="x")  # type: ignore[call-arg]


@pytest.mark.asyncio
async def test_a_proposal_for_a_new_page_creates_no_page(gate: _RecordingGate) -> None:
    """An unapproved page must not appear in the team's rail. The page row is
    created at approval, which is why the proposal carries the title itself."""

    store = _Store()

    result = await wiki_service.propose_wiki_page(
        _user(),
        TEAM,
        ProposePageRequest(title="Shinigami", content_md="text"),
        _deps(store),
    )

    assert result.kind == "page"
    assert store.pages == []


@pytest.mark.asyncio
async def test_a_restore_cannot_launder_a_proposal_into_history(
    gate: _RecordingGate,
) -> None:
    """Restoring a `proposed` revision would publish an agent's draft as a
    human edit AND clear the review mark — undoing the decision the approval
    gate exists to record, with one id and no approval at all."""

    store = _Store()
    store.pages.append(_page("p1", None))
    store.revisions["draft-1"] = _revision("draft-1", "p1", status="proposed")
    deps = _deps(store)

    with pytest.raises(wiki_service.WikiRequestError) as caught:
        await wiki_service.restore_wiki_revision(_user(), TEAM, "p1", "draft-1", deps)
    assert caught.value.http_status == 404


# ── history pagination (WIKI-05) ──────────────────────────────────────────────


def _at(offset_seconds: int) -> datetime:
    """A deterministic, tz-aware timestamp — real revisions are UTC and a
    cursor round-trip that silently dropped the offset would misplace every
    boundary condition below."""

    return datetime(2026, 9, 1, tzinfo=timezone.utc) + timedelta(seconds=offset_seconds)


def _hex_id(i: int) -> str:
    """A 32-char lowercase hex id shaped like `_new_id()`'s — the cursor
    validates against exactly that shape, so a test id must satisfy it too."""

    return f"{i:032x}"


@pytest.mark.asyncio
async def test_a_cursor_round_trips_through_the_service(gate: _RecordingGate) -> None:
    store = _Store()
    store.pages.append(_page("p1", None))
    store.revisions = {
        _hex_id(i): _revision(_hex_id(i), "p1", created_at=_at(i)) for i in range(3)
    }

    first = await wiki_service.list_wiki_revisions(_user(), TEAM, "p1", _deps(store))
    assert [r.revision_id for r in first.revisions] == [
        _hex_id(2),
        _hex_id(1),
        _hex_id(0),
    ]
    assert first.next_cursor is None  # fewer than one page — nothing further


@pytest.mark.asyncio
async def test_a_full_page_gets_a_next_cursor_from_the_last_returned_row(
    gate: _RecordingGate,
) -> None:
    """The `limit + 1` trick: one extra row is fetched to learn there is more,
    then dropped — `next_cursor` must anchor on the last row actually handed
    back, not on that extra one, or a walk would silently skip a revision."""

    store = _Store()
    store.pages.append(_page("p1", None))
    total = MAX_REVISION_PAGE_SIZE + 5
    store.revisions = {
        _hex_id(i): _revision(_hex_id(i), "p1", created_at=_at(i)) for i in range(total)
    }

    first = await wiki_service.list_wiki_revisions(_user(), TEAM, "p1", _deps(store))
    assert len(first.revisions) == MAX_REVISION_PAGE_SIZE
    assert first.next_cursor is not None

    oldest_on_first_page = first.revisions[-1]
    decoded = wiki_service._decode_revision_cursor(first.next_cursor)
    assert decoded.revision_id == oldest_on_first_page.revision_id
    assert decoded.created_at == oldest_on_first_page.created_at

    second = await wiki_service.list_wiki_revisions(
        _user(), TEAM, "p1", _deps(store), cursor=first.next_cursor
    )
    assert len(second.revisions) == 5
    assert second.next_cursor is None
    seen = {r.revision_id for r in first.revisions} | {
        r.revision_id for r in second.revisions
    }
    assert len(seen) == total  # every revision exactly once, no gap or repeat


@pytest.mark.asyncio
async def test_tied_created_at_does_not_destabilize_the_walk(
    gate: _RecordingGate,
) -> None:
    """Several revisions sharing one timestamp is ordinary (an edit then a
    restore inside the same second) — the walk must still be exact, broken
    only by `revision_id`."""

    store = _Store()
    store.pages.append(_page("p1", None))
    same_instant = _at(0)
    total = MAX_REVISION_PAGE_SIZE + 3
    store.revisions = {
        _hex_id(i): _revision(_hex_id(i), "p1", created_at=same_instant)
        for i in range(total)
    }

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):  # generous bound: two pages expected, never an endless loop
        page = await wiki_service.list_wiki_revisions(
            _user(), TEAM, "p1", _deps(store), cursor=cursor
        )
        if not page.revisions:
            break
        seen.extend(r.revision_id for r in page.revisions)
        cursor = page.next_cursor
        if cursor is None:
            break

    assert cursor is None
    assert sorted(seen) == sorted(store.revisions.keys())
    assert len(set(seen)) == total  # no duplicate despite the identical timestamp


@pytest.mark.asyncio
async def test_an_invalid_cursor_is_refused_not_500(gate: _RecordingGate) -> None:
    store = _Store()
    store.pages.append(_page("p1", None))

    for bad in [
        "not-base64!!",
        "   ",
        base64.urlsafe_b64encode(b"no-separator-here").decode(),
    ]:
        with pytest.raises(wiki_service.WikiRequestError) as caught:
            await wiki_service.list_wiki_revisions(
                _user(), TEAM, "p1", _deps(store), cursor=bad
            )
        assert caught.value.http_status == 400


@pytest.mark.asyncio
async def test_an_empty_cursor_is_treated_as_no_cursor(gate: _RecordingGate) -> None:
    """An omitted `cursor` and an empty one both mean "start from the top" —
    a query string can produce either depending on the client, and neither is
    a malformed value worth a 400 for."""

    store = _Store()
    store.pages.append(_page("p1", None))
    store.revisions[_hex_id(1)] = _revision(_hex_id(1), "p1", created_at=_at(0))

    result = await wiki_service.list_wiki_revisions(
        _user(), TEAM, "p1", _deps(store), cursor=""
    )
    assert [r.revision_id for r in result.revisions] == [_hex_id(1)]


@pytest.mark.asyncio
async def test_a_well_formed_but_fabricated_cursor_is_refused(
    gate: _RecordingGate,
) -> None:
    """Right shape, wrong content: a naive/timezone-less timestamp or a
    revision id that isn't `_new_id()`'s hex format must not reach the store
    as a query bound."""

    store = _Store()
    store.pages.append(_page("p1", None))

    naive_cursor = base64.urlsafe_b64encode(
        f"2026-09-01T00:00:00|{_hex_id(1)}".encode()
    ).decode()
    short_id_cursor = base64.urlsafe_b64encode(
        f"{_at(0).isoformat()}|short-id".encode()
    ).decode()

    for cursor in (naive_cursor, short_id_cursor):
        with pytest.raises(wiki_service.WikiRequestError) as caught:
            await wiki_service.list_wiki_revisions(
                _user(), TEAM, "p1", _deps(store), cursor=cursor
            )
        assert caught.value.http_status == 400


@pytest.mark.asyncio
async def test_a_cursor_never_crosses_a_page_boundary(gate: _RecordingGate) -> None:
    """The cursor is a position within one page's history, not a bypass for
    the page/team scope the store filters on independently."""

    store = _Store()
    store.pages.append(_page("p1", None))
    store.pages.append(_page("p2", None))
    store.revisions[_hex_id(1)] = _revision(_hex_id(1), "p1", created_at=_at(0))
    store.revisions[_hex_id(2)] = _revision(_hex_id(2), "p2", created_at=_at(1))

    cursor = wiki_service._encode_revision_cursor(_at(5), _hex_id(9))
    result = await wiki_service.list_wiki_revisions(
        _user(), TEAM, "p2", _deps(store), cursor=cursor
    )
    assert [r.revision_id for r in result.revisions] == [_hex_id(2)]
