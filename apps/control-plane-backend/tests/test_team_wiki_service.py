from __future__ import annotations

from typing import Any

import pytest
from control_plane_backend.models.team_wiki_models import RULES_PAGE_SLUG
from control_plane_backend.team_wiki import service as wiki_service
from control_plane_backend.team_wiki.schemas import (
    CreateWikiPageRequest,
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
    slugify,
)
from control_plane_backend.team_wiki.store import WikiPageRecord
from fred_core.common import TeamId

TEAM = TeamId("team-a")


# ── pure helpers ─────────────────────────────────────────────────────────────


def test_slugify_folds_accents_instead_of_dropping_the_words() -> None:
    # Dropping non-ASCII would turn this into "d-quipe"; folding keeps the word.
    assert slugify("Décisions d'équipe") == "decisions-d-equipe"


def test_slugify_never_returns_an_empty_slug() -> None:
    assert slugify("!!!") == "page"
    assert slugify("") == "page"


def _page(page_id: str, parent: str | None) -> WikiPageRecord:
    return WikiPageRecord(
        page_id=page_id,
        team_id=TEAM,
        slug=page_id,
        title=page_id,
        parent_page_id=parent,
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

    async def list_pages(self, _team_id: TeamId) -> list[WikiPageRecord]:
        return self.pages

    async def get_page(self, _team_id: TeamId, page_id: str) -> WikiPageRecord | None:
        return next((p for p in self.pages if p.page_id == page_id), None)

    async def get_page_by_slug(
        self, _team_id: TeamId, slug: str
    ) -> WikiPageRecord | None:
        return next((p for p in self.pages if p.slug == slug), None)

    async def get_revision(self, _team_id: TeamId, _revision_id: str) -> None:
        return None


class _Deps:
    team_dependencies = object()

    def __init__(self, store: _Store) -> None:
        self._store = store

    def get_team_wiki_store(self) -> Any:
        return self._store


@pytest.fixture()
def gate(monkeypatch: pytest.MonkeyPatch) -> _RecordingGate:
    recorder = _RecordingGate()
    monkeypatch.setattr(wiki_service, "require_team_access", recorder)
    return recorder


@pytest.mark.asyncio
async def test_reads_demand_a_member_only_permission(gate: _RecordingGate) -> None:
    """`CAN_READ` would admit non-members of a PUBLIC team; the wiki holds a
    team's internal knowledge, so the read gate must be member-only."""

    deps = _Deps(_Store())
    await wiki_service.get_wiki_tree(_User(), TEAM, deps)  # type: ignore[arg-type]
    assert gate.permissions == [[WIKI_READ_PERMISSION]]
    assert WIKI_READ_PERMISSION.value == "can_read_members"


@pytest.mark.asyncio
async def test_every_write_demands_the_editor_permission(gate: _RecordingGate) -> None:
    """One test over all of them: a write path that forgets its gate is the
    failure this covers, and it is easiest to miss on the least-used route."""

    store = _Store()
    store.pages.append(_page("p1", None))
    deps = _Deps(store)
    user = _User()

    with pytest.raises(Exception):
        await wiki_service.create_wiki_page(  # type: ignore[arg-type]
            user, TEAM, CreateWikiPageRequest(title="T"), deps
        )
    with pytest.raises(Exception):
        await wiki_service.update_wiki_page_content(  # type: ignore[arg-type]
            user, TEAM, "p1", UpdateWikiPageContentRequest(content_md="x"), deps
        )
    with pytest.raises(Exception):
        await wiki_service.update_wiki_page_metadata(  # type: ignore[arg-type]
            user, TEAM, "p1", UpdateWikiPageMetadataRequest(title="T2"), deps
        )
    with pytest.raises(Exception):
        await wiki_service.update_wiki_rules(  # type: ignore[arg-type]
            user, TEAM, UpdateWikiRulesRequest(content_md="x"), deps
        )
    with pytest.raises(Exception):
        await wiki_service.set_wiki_page_needs_review(  # type: ignore[arg-type]
            user, TEAM, "p1", SetNeedsReviewRequest(needs_review=False), deps
        )
    with pytest.raises(Exception):
        await wiki_service.delete_wiki_page(user, TEAM, "p1", deps)  # type: ignore[arg-type]
    with pytest.raises(Exception):
        await wiki_service.restore_wiki_revision(user, TEAM, "p1", "r1", deps)  # type: ignore[arg-type]

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
    deps = _Deps(store)
    user = _User()

    with pytest.raises(WikiRequestError) as edit:
        await wiki_service.update_wiki_page_content(  # type: ignore[arg-type]
            user,
            TEAM,
            "rules-1",
            UpdateWikiPageContentRequest(content_md="hacked"),
            deps,
        )
    assert edit.value.http_status == 400

    with pytest.raises(WikiRequestError) as move:
        await wiki_service.update_wiki_page_metadata(  # type: ignore[arg-type]
            user,
            TEAM,
            "rules-1",
            UpdateWikiPageMetadataRequest(title="Not rules"),
            deps,
        )
    assert move.value.http_status == 400

    with pytest.raises(WikiRequestError) as removed:
        await wiki_service.delete_wiki_page(user, TEAM, "rules-1", deps)  # type: ignore[arg-type]
    assert removed.value.http_status == 400


@pytest.mark.asyncio
async def test_a_page_cannot_be_moved_under_its_own_child(gate: _RecordingGate) -> None:
    store = _Store()
    store.pages.extend([_page("root", None), _page("child", "root")])
    deps = _Deps(store)

    with pytest.raises(WikiRequestError) as caught:
        await wiki_service.update_wiki_page_metadata(  # type: ignore[arg-type]
            _User(),
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
    deps = _Deps(store)

    with pytest.raises(WikiRequestError):
        await wiki_service.update_wiki_page_metadata(  # type: ignore[arg-type]
            _User(), TEAM, "p", UpdateWikiPageMetadataRequest(parent_page_id="p"), deps
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
    deps = _Deps(store)

    # Moving "a" (height 2) under "dest-child" (child depth 2) would land "c" at
    # depth 4, past MAX_PAGE_DEPTH.
    with pytest.raises(WikiRequestError) as caught:
        await wiki_service.update_wiki_page_metadata(  # type: ignore[arg-type]
            _User(),
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

    deps = _Deps(_NoWriteStore())
    detail = await wiki_service.get_wiki_rules(_User(), TEAM, deps)  # type: ignore[arg-type]
    assert detail.content_md == ""
    assert detail.revision_id is None
    assert detail.page.kind == "rules"
    assert gate.permissions == [[WIKI_READ_PERMISSION]]
