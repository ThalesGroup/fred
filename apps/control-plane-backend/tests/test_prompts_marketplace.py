"""Store-level tests for the prompts marketplace (PROMPT-06).

Covers the new `PromptStore` primitives the marketplace is built on:
- `set_published` flips the live visibility flag on the team's own row,
- `list_published` returns published prompts across all teams, most-used first,
- `increment_session_count_global` counts a marketplace "use" by prompt id
  alone (the caller need not be a member of the author team),
- the `_imported-N` copy-by-value naming used by marketplace import.

These run fully offline against a temporary SQLite file — no infra, no rebac.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fred_core.common import TeamId
from sqlalchemy.ext.asyncio import create_async_engine

from control_plane_backend.models.base import Base as CPBase
from control_plane_backend.product.service import _next_imported_name
from control_plane_backend.prompts.store import PromptRecord, PromptStore


@pytest_asyncio.fixture
async def store(tmp_path) -> AsyncIterator[PromptStore]:
    db_path = tmp_path / "marketplace_test.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(CPBase.metadata.create_all)
    try:
        yield PromptStore(engine)
    finally:
        await engine.dispose()


def _record(team: str, name: str, text: str = "hello") -> PromptRecord:
    return PromptRecord(
        prompt_id=f"{team}:{name}",
        team_id=TeamId(team),
        name=name,
        description=None,
        text=text,
        created_by="u1",
    )


@pytest.mark.asyncio
async def test_new_prompt_is_unpublished_by_default(store: PromptStore) -> None:
    created = await store.create(_record("team-a", "p1"))
    assert created.published is False


@pytest.mark.asyncio
async def test_set_published_toggles_flag_and_is_scoped(store: PromptStore) -> None:
    await store.create(_record("team-a", "p1"))

    published = await store.set_published("team-a:p1", TeamId("team-a"), True)
    assert published is not None
    assert published.published is True

    # Wrong owning team: no row updated, returns None, flag unchanged.
    assert await store.set_published("team-a:p1", TeamId("team-b"), False) is None
    still = await store.get("team-a:p1")
    assert still is not None and still.published is True

    unpublished = await store.set_published("team-a:p1", TeamId("team-a"), False)
    assert unpublished is not None and unpublished.published is False


@pytest.mark.asyncio
async def test_list_published_spans_teams_ordered_by_usage(store: PromptStore) -> None:
    await store.create(_record("team-a", "low"))
    await store.create(_record("team-b", "high"))
    await store.create(_record("team-a", "hidden"))  # stays unpublished

    await store.set_published("team-a:low", TeamId("team-a"), True)
    await store.set_published("team-b:high", TeamId("team-b"), True)
    # "high" gets more usage → should sort first.
    for _ in range(3):
        await store.increment_session_count_global("team-b:high")

    published = await store.list_published()
    names = [r.name for r in published]
    assert names == ["high", "low"]
    assert {r.team_id for r in published} == {TeamId("team-a"), TeamId("team-b")}


@pytest.mark.asyncio
async def test_increment_session_count_global_by_id(store: PromptStore) -> None:
    await store.create(_record("team-a", "p1"))
    assert await store.increment_session_count_global("team-a:p1") is True
    assert await store.increment_session_count_global("missing") is False
    row = await store.get("team-a:p1")
    assert row is not None and row.session_count == 1


@pytest.mark.asyncio
async def test_next_imported_name_increments_suffix(store: PromptStore) -> None:
    target = TeamId("team-a")
    first = await _next_imported_name(store, target, "Great prompt")
    assert first == "Great prompt_imported-1"

    await store.create(_record("team-a", "Great prompt_imported-1"))
    second = await _next_imported_name(store, target, "Great prompt")
    assert second == "Great prompt_imported-2"
