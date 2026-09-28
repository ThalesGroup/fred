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

"""Store-level tests for the prompts marketplace (PROMPT-06).

Covers the new `PromptStore` primitives the marketplace is built on:
- `set_published` flips the live visibility flag on the team's own row,
- `list_published` returns published prompts across all teams, most-used first,
- `increment_session_count_global` counts a marketplace "use" by prompt id
  alone (the caller need not be a member of the author team),
- the `_imported-N` copy-by-value naming used by marketplace import, and
  the `-N` command suffixing that keeps an import from ever being blocked.

These run fully offline against a temporary SQLite file — no infra, no rebac.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

import pytest
import pytest_asyncio
from control_plane_backend.models.base import Base as CPBase
from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.product.schemas import (
    COMMAND_MAX_LENGTH,
    MarketplacePromptDetail,
    MarketplacePromptSummary,
)
from control_plane_backend.product.service import (
    _next_imported_command,
    _next_imported_name,
    import_published_prompt_into_team,
)
from control_plane_backend.prompts.store import PromptRecord, PromptStore
from fred_core import KeycloakUser
from fred_core.common import TeamId
from sqlalchemy.ext.asyncio import create_async_engine


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


def _record(
    team: str, name: str, text: str = "hello", command: str | None = None
) -> PromptRecord:
    return PromptRecord(
        prompt_id=f"{team}:{name}",
        team_id=TeamId(team),
        name=name,
        description=None,
        command=command,
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


@pytest.mark.asyncio
async def test_next_imported_command_keeps_a_free_command(store: PromptStore) -> None:
    """A free command is kept as authored — unlike the name, always suffixed.

    A command is meant to be typed, so `summary` is worth keeping when nothing
    in the target team claims it.
    """

    assert await _next_imported_command(store, TeamId("team-a"), "summary") == "summary"


@pytest.mark.asyncio
async def test_next_imported_command_suffixes_from_two(store: PromptStore) -> None:
    target = TeamId("team-a")
    await store.create(_record("team-a", "Held", command="summary"))
    assert await _next_imported_command(store, target, "summary") == "summary-2"

    await store.create(_record("team-a", "Held two", command="summary-2"))
    assert await _next_imported_command(store, target, "summary") == "summary-3"


@pytest.mark.asyncio
async def test_next_imported_command_is_team_local(store: PromptStore) -> None:
    await store.create(_record("team-b", "Held", command="summary"))
    assert await _next_imported_command(store, TeamId("team-a"), "summary") == "summary"


@pytest.mark.asyncio
async def test_next_imported_command_passes_absence_through(
    store: PromptStore,
) -> None:
    """A prompt with no command imports with none — no suffix is invented."""

    assert await _next_imported_command(store, TeamId("team-a"), None) is None


@pytest.mark.asyncio
async def test_next_imported_command_trims_the_base_to_fit(
    store: PromptStore,
) -> None:
    """The suffix must fit the column, so the base gives way, not the suffix."""

    base = "c" * COMMAND_MAX_LENGTH
    await store.create(_record("team-a", "Held", command=base))
    suffixed = await _next_imported_command(store, TeamId("team-a"), base)
    assert suffixed is not None
    assert len(suffixed) == COMMAND_MAX_LENGTH
    assert suffixed.endswith("-2")


class _Deps:
    """Minimal `ProductServiceDependencies` stand-in: the import only reads the
    prompt store."""

    def __init__(self, store: PromptStore) -> None:
        self._store = store

    def get_prompt_store(self) -> PromptStore:
        return self._store


class _User:
    uid = "importer"


def _deps(store: PromptStore) -> ProductServiceDependencies:
    return cast(ProductServiceDependencies, _Deps(store))


def _user() -> KeycloakUser:
    return cast(KeycloakUser, _User())


@pytest.mark.asyncio
async def test_import_copies_the_command_then_suffixes_the_next_one(
    store: PromptStore,
) -> None:
    """Importing twice into one team never fails on the command.

    The first copy keeps `summary`; the second takes `summary-2`, the way the
    name already takes `_imported-2`.
    """

    source = _record("team-src", "Great prompt", command="summary")
    source.published = True
    await store.create(source)
    deps = _deps(store)

    first = await import_published_prompt_into_team(
        _user(), source.prompt_id, TeamId("team-a"), deps
    )
    second = await import_published_prompt_into_team(
        _user(), source.prompt_id, TeamId("team-a"), deps
    )

    assert first.command == "summary"
    assert second.command == "summary-2"
    # The author's own prompt is untouched.
    held = await store.get(source.prompt_id)
    assert held is not None and held.command == "summary"


@pytest.mark.asyncio
async def test_import_of_a_prompt_without_a_command_invents_none(
    store: PromptStore,
) -> None:
    source = _record("team-src", "Plain prompt")
    source.published = True
    await store.create(source)

    imported = await import_published_prompt_into_team(
        _user(), source.prompt_id, TeamId("team-a"), _deps(store)
    )

    assert imported.command is None


def test_marketplace_projections_expose_the_command() -> None:
    """The import reads the command off a marketplace payload, so it must be
    there. Both marketplace shapes inherit it from the team projections; this
    pins that inheritance rather than trusting it."""

    assert "command" in MarketplacePromptSummary.model_fields
    assert "command" in MarketplacePromptDetail.model_fields


@pytest.mark.asyncio
async def test_next_imported_command_sees_commands_past_a_listing_page(
    store: PromptStore,
) -> None:
    """The suffixer must see every command the team holds.

    A row-limited listing would hide a held command behind newer rows and
    hand back a value the unique index then refuses — a 409 where the import
    should simply have suffixed.
    """

    for i in range(1200):
        await store.create(_record("team-a", f"Filler {i}", command=f"cmd-{i}"))

    assert await _next_imported_command(store, TeamId("team-a"), "cmd-0") == "cmd-0-2"
