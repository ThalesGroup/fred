from __future__ import annotations

from typing import Any, cast

import pytest
from control_plane_backend.models.team_wiki_models import RULES_PAGE_SLUG
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
    _child_depth_under,
    _is_descendant,
    _subtree_height,
    _unique_slug,
)
from control_plane_backend.team_wiki.store import WikiPageRecord, WikiRevisionRecord
from fred_core import KeycloakUser
from fred_core.common import TeamId

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
    revision_id: str, page_id: str, *, status: str = "published"
) -> WikiRevisionRecord:
    return WikiRevisionRecord(
        revision_id=revision_id,
        page_id=page_id,
        team_id=TEAM,
        content_md="body",
        status=status,
    )


def test_child_depth_is_the_depth_the_child_would_sit_at() -> None:
    """A root page is depth 0, so a child of a root is 1. The helper is named
    for what it returns: read as "depth of the parent", the cap lands a tier
    out."""

    pages = {"a": _page("a", None), "b": _page("b", "a"), "c": _page("c", "b")}
    assert _child_depth_under(pages, None) == 0
    assert _child_depth_under(pages, "a") == 1
    assert _child_depth_under(pages, "c") == 3


def test_child_depth_terminates_on_a_cycle() -> None:
    """A cycle should be impossible, but a bounded walk means a corrupted row
    cannot hang a request while someone works out why."""

    pages = {"a": _page("a", "b"), "b": _page("b", "a")}
    assert _child_depth_under(pages, "a") <= 10


def test_subtree_height_is_zero_for_a_leaf_and_counts_levels_below() -> None:
    pages = {
        "root": _page("root", None),
        "child": _page("child", "root"),
        "grandchild": _page("grandchild", "child"),
    }
    assert _subtree_height(pages, "grandchild") == 0
    assert _subtree_height(pages, "child") == 1
    assert _subtree_height(pages, "root") == 2


def test_is_descendant_detects_the_move_that_would_detach_a_subtree() -> None:
    pages = {
        "root": _page("root", None),
        "child": _page("child", "root"),
        "grandchild": _page("grandchild", "child"),
    }
    assert _is_descendant(pages, "grandchild", "root") is True
    assert _is_descendant(pages, "root", "grandchild") is False


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
    """Enough store for the gate tests: every write is refused before it runs,
    so nothing here needs to behave."""

    def __init__(self) -> None:
        self.pages: list[WikiPageRecord] = []
        self.revisions: dict[str, WikiRevisionRecord] = {}
        self.proposals: list[WikiRevisionRecord] = []

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

    with pytest.raises(Exception):
        await wiki_service.create_wiki_page(
            user, TEAM, CreateWikiPageRequest(title="T"), deps
        )
    with pytest.raises(Exception):
        await wiki_service.update_wiki_page_content(
            user, TEAM, "p1", UpdateWikiPageContentRequest(content_md="x"), deps
        )
    with pytest.raises(Exception):
        await wiki_service.update_wiki_page_metadata(
            user, TEAM, "p1", UpdateWikiPageMetadataRequest(title="T2"), deps
        )
    with pytest.raises(Exception):
        await wiki_service.update_wiki_rules(
            user, TEAM, UpdateWikiRulesRequest(content_md="x"), deps
        )
    with pytest.raises(Exception):
        await wiki_service.set_wiki_page_needs_review(
            user, TEAM, "p1", SetNeedsReviewRequest(needs_review=False), deps
        )
    with pytest.raises(Exception):
        await wiki_service.delete_wiki_page(user, TEAM, "p1", deps)
    with pytest.raises(Exception):
        await wiki_service.restore_wiki_revision(user, TEAM, "p1", "r1", deps)

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


@pytest.mark.asyncio
async def test_a_page_cannot_be_moved_under_its_own_child(gate: _RecordingGate) -> None:
    store = _Store()
    store.pages.extend([_page("root", None), _page("child", "root")])
    deps = _deps(store)

    with pytest.raises(WikiRequestError) as caught:
        await wiki_service.update_wiki_page_metadata(
            _user(),
            TEAM,
            "root",
            UpdateWikiPageMetadataRequest(parent_page_id="child"),
            deps,
        )
    assert caught.value.http_status == 400
    assert "children" in str(caught.value)


@pytest.mark.asyncio
async def test_a_page_cannot_be_its_own_parent(gate: _RecordingGate) -> None:
    store = _Store()
    store.pages.append(_page("p", None))
    deps = _deps(store)

    with pytest.raises(WikiRequestError):
        await wiki_service.update_wiki_page_metadata(
            _user(), TEAM, "p", UpdateWikiPageMetadataRequest(parent_page_id="p"), deps
        )


@pytest.mark.asyncio
async def test_a_move_accounts_for_the_subtree_it_carries(gate: _RecordingGate) -> None:
    """Checking only the destination's depth lets create-then-move defeat the
    cap: the pages are shallow one at a time, deep once attached."""

    store = _Store()
    # A three-level stack, plus a destination already one level down.
    store.pages.extend(
        [
            _page("a", None),
            _page("b", "a"),
            _page("c", "b"),
            _page("dest", None),
            _page("dest-child", "dest"),
        ]
    )
    deps = _deps(store)

    # Moving "a" (height 2) under "dest-child" (child depth 2) would land "c" at
    # depth 4, past MAX_PAGE_DEPTH.
    with pytest.raises(WikiRequestError) as caught:
        await wiki_service.update_wiki_page_metadata(
            _user(),
            TEAM,
            "a",
            UpdateWikiPageMetadataRequest(parent_page_id="dest-child"),
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
            ProposeEditRequest(slug="__rules__", content_md="anything"),
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
        _user(), TEAM, ProposeEditRequest(slug="notes", content_md="new text"), deps
    )

    assert result.kind == "edit"
    assert store.proposals[0].status == "proposed"
    assert page.current_revision_id == "rev-p1"


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
