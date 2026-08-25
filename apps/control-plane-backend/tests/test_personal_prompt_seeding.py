"""Personal spaces get the prompt starter kit too (#2410).

Personal teams are *virtual* (`teams/system.py::build_personal_team`): they are
synthesized as `personal-<uid>` on the fly, never go through `create_team`, and
own no `teammetadata` row - so PROMPT-09's creation-time seeding and its
backfill migration both missed them entirely. The fix seeds them lazily, on the
first read of any prompt surface, using the same shared `seed_starter_kit`.

These run fully offline against a temporary SQLite file so the stores' real
`(team_id, name)` unique constraints - the whole basis of the convergent
create-or-reuse behaviour asserted below - are actually exercised.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from control_plane_backend.models.base import Base as CPBase
from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.product.prompt_starter_kit import (
    STARTER_CATEGORY_NAMES,
    STARTER_PROMPTS,
    seed_starter_kit,
)
from control_plane_backend.product.service import (
    _ensure_personal_starter_kit,
    list_prompt_categories,
    list_prompts,
)
from control_plane_backend.prompts.category_store import (
    PromptCategoryRecord,
    PromptCategoryStore,
)
from control_plane_backend.prompts.store import PromptRecord, PromptStore
from fred_core.common import TeamId
from sqlalchemy.ext.asyncio import create_async_engine

PERSONAL_TEAM = TeamId("personal-alice-uid")
COLLAB_TEAM = TeamId("swiftpost-team-id")


class _Stores:
    def __init__(self, prompts: PromptStore, categories: PromptCategoryStore) -> None:
        self.prompts = prompts
        self.categories = categories


@pytest_asyncio.fixture
async def stores(tmp_path) -> AsyncIterator[_Stores]:
    db_path = tmp_path / "personal_seeding_test.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(CPBase.metadata.create_all)
    try:
        yield _Stores(PromptStore(engine), PromptCategoryStore(engine))
    finally:
        await engine.dispose()


def _deps(stores: _Stores, *, prompt_store: Any = None) -> ProductServiceDependencies:
    """A `ProductServiceDependencies` carrying real prompt stores and nothing else.

    Every other collaborator is a `MagicMock`: the seeding path must not touch
    ReBAC, sessions, KPI, or the scheduler, and a mock would blow up loudly if
    it ever did.
    """

    deps = MagicMock(spec=ProductServiceDependencies)
    deps.get_prompt_store = lambda: prompt_store or stores.prompts
    deps.get_prompt_category_store = lambda: stores.categories
    return cast(ProductServiceDependencies, deps)


async def _names(stores: _Stores, team_id: TeamId) -> tuple[list[str], list[str]]:
    prompts = await stores.prompts.list_by_team(team_id)
    categories = await stores.categories.list_by_team(team_id)
    return sorted(p.name for p in prompts), sorted(c.name for c in categories)


# --------------------------- seed_starter_kit (shared core) -----------------


@pytest.mark.asyncio
async def test_seed_creates_the_full_kit_linked_to_its_categories(
    stores: _Stores,
) -> None:
    await seed_starter_kit(
        COLLAB_TEAM, prompt_store=stores.prompts, category_store=stores.categories
    )

    prompts = await stores.prompts.list_by_team(COLLAB_TEAM)
    categories = await stores.categories.list_by_team(COLLAB_TEAM)
    assert sorted(c.name for c in categories) == sorted(STARTER_CATEGORY_NAMES)
    assert sorted(p.name for p in prompts) == sorted(s.name for s in STARTER_PROMPTS)

    category_name_by_id = {c.category_id: c.name for c in categories}
    expected_category_by_prompt = {s.name: s.category_name for s in STARTER_PROMPTS}
    for prompt in prompts:
        assert prompt.category_id is not None
        assert (
            category_name_by_id[prompt.category_id]
            == expected_category_by_prompt[prompt.name]
        )
        # Seeded content is authored by the platform, not by a user, and is
        # never auto-published to the marketplace (PROMPT-06).
        assert prompt.created_by is None
        assert prompt.published is False


@pytest.mark.asyncio
async def test_seeding_twice_converges_instead_of_duplicating(stores: _Stores) -> None:
    """Convergence matters because the personal-space caller is a *read* path:
    two concurrent first visits would otherwise race into duplicate rows (or a
    500 from the unique constraint)."""

    await seed_starter_kit(
        PERSONAL_TEAM, prompt_store=stores.prompts, category_store=stores.categories
    )
    await seed_starter_kit(
        PERSONAL_TEAM, prompt_store=stores.prompts, category_store=stores.categories
    )

    prompt_names, category_names = await _names(stores, PERSONAL_TEAM)
    assert len(category_names) == len(STARTER_CATEGORY_NAMES)
    assert len(prompt_names) == len(STARTER_PROMPTS)


@pytest.mark.asyncio
async def test_seed_reuses_a_pre_existing_category_of_the_same_name(
    stores: _Stores,
) -> None:
    """A name collision must reuse the existing row, not orphan the prompt that
    belongs in it: the "Communication" starter prompt still has to resolve to
    the category id that was already there."""

    existing = await stores.categories.create(
        PromptCategoryRecord(
            category_id="pre-existing", team_id=PERSONAL_TEAM, name="Communication"
        )
    )

    await seed_starter_kit(
        PERSONAL_TEAM, prompt_store=stores.prompts, category_store=stores.categories
    )

    categories = await stores.categories.list_by_team(PERSONAL_TEAM)
    assert sorted(c.name for c in categories) == sorted(STARTER_CATEGORY_NAMES)
    assert len([c for c in categories if c.name == "Communication"]) == 1

    spec = next(s for s in STARTER_PROMPTS if s.category_name == "Communication")
    prompts = await stores.prompts.list_by_team(PERSONAL_TEAM)
    seeded = next(p for p in prompts if p.name == spec.name)
    assert seeded.category_id == existing.category_id


# --------------------------- _ensure_personal_starter_kit -------------------


@pytest.mark.asyncio
async def test_ensure_seeds_a_pristine_personal_space(stores: _Stores) -> None:
    await _ensure_personal_starter_kit(PERSONAL_TEAM, _deps(stores))

    prompt_names, category_names = await _names(stores, PERSONAL_TEAM)
    assert len(category_names) == len(STARTER_CATEGORY_NAMES)
    assert len(prompt_names) == len(STARTER_PROMPTS)


@pytest.mark.asyncio
async def test_ensure_is_a_no_op_for_a_collaborative_team(stores: _Stores) -> None:
    """Collaborative teams are already seeded at creation time; re-seeding them
    on read would resurrect content their editors deliberately deleted."""

    await _ensure_personal_starter_kit(COLLAB_TEAM, _deps(stores))

    assert await _names(stores, COLLAB_TEAM) == ([], [])


@pytest.mark.asyncio
async def test_ensure_leaves_a_personal_space_that_has_prompts_alone(
    stores: _Stores,
) -> None:
    await stores.prompts.create(
        PromptRecord(
            prompt_id="p1",
            team_id=PERSONAL_TEAM,
            name="my own prompt",
            description=None,
            text="hello",
            created_by="alice-uid",
        )
    )

    await _ensure_personal_starter_kit(PERSONAL_TEAM, _deps(stores))

    prompt_names, category_names = await _names(stores, PERSONAL_TEAM)
    assert prompt_names == ["my own prompt"]
    assert category_names == []


@pytest.mark.asyncio
async def test_ensure_leaves_a_personal_space_that_has_only_categories_alone(
    stores: _Stores,
) -> None:
    """Categories without prompts is a real state (the user emptied their
    library but kept their taxonomy) - pristine means *both* are empty."""

    await stores.categories.create(
        PromptCategoryRecord(
            category_id="c1", team_id=PERSONAL_TEAM, name="Mes catégories"
        )
    )

    await _ensure_personal_starter_kit(PERSONAL_TEAM, _deps(stores))

    prompt_names, category_names = await _names(stores, PERSONAL_TEAM)
    assert prompt_names == []
    assert category_names == ["Mes catégories"]


@pytest.mark.asyncio
async def test_ensure_swallows_store_failures(stores: _Stores) -> None:
    """Best-effort: seeding is a side effect of a listing call, so a store
    failure must degrade to an empty library, never a 500 on the listing."""

    failing = MagicMock()

    async def _boom(*_a, **_k):
        raise RuntimeError("db unavailable")

    failing.list_by_team = _boom

    await _ensure_personal_starter_kit(
        PERSONAL_TEAM, _deps(stores, prompt_store=failing)
    )

    assert await _names(stores, PERSONAL_TEAM) == ([], [])


# --------------------------- service read surfaces --------------------------


@pytest.mark.asyncio
async def test_list_prompts_seeds_the_personal_space_on_first_read(
    stores: _Stores,
) -> None:
    summaries = await list_prompts(PERSONAL_TEAM, _deps(stores))
    assert sorted(s.name for s in summaries) == sorted(s.name for s in STARTER_PROMPTS)

    categories = await list_prompt_categories(PERSONAL_TEAM, _deps(stores))
    assert sorted(c.name for c in categories) == sorted(STARTER_CATEGORY_NAMES)
    # Second read returns the same kit, not a duplicated one.
    assert len(await list_prompts(PERSONAL_TEAM, _deps(stores))) == len(STARTER_PROMPTS)


@pytest.mark.asyncio
async def test_list_prompts_does_not_seed_a_collaborative_team(
    stores: _Stores,
) -> None:
    assert await list_prompts(COLLAB_TEAM, _deps(stores)) == []
    assert await list_prompt_categories(COLLAB_TEAM, _deps(stores)) == []


@pytest.mark.asyncio
async def test_list_prompts_survives_a_seeding_failure(stores: _Stores) -> None:
    class _FailOnSeedOnly:
        """Reports an empty library, then fails the seeding write."""

        async def list_by_team(self, *_a, **_k):
            return []

        async def create(self, *_a, **_k):
            raise RuntimeError("db unavailable")

    assert (
        await list_prompts(PERSONAL_TEAM, _deps(stores, prompt_store=_FailOnSeedOnly()))
        == []
    )
