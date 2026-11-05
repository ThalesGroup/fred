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

"""The real SQL analysis store on an in-memory SQLite database, shared by every
"replica" a test builds."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from fred_capability_ppt_filler.builder import analysis_job, deck_plans
from fred_capability_ppt_filler.builder.analysis_job import (
    PptBuilderBase,
    SqlAnalysisStore,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


@pytest.fixture(autouse=True)
def deck_plan_store() -> Iterator[deck_plans.MemoryDeckPlanStore]:
    """Base plans in memory: a build never reaches the pod's Postgres in tests."""
    store = deck_plans.MemoryDeckPlanStore()
    deck_plans.set_deck_plan_store_provider(lambda: store)
    yield store
    deck_plans.clear_deck_plan_store_provider()


@pytest_asyncio.fixture
async def analysis_db(
    tmp_path: Path,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    # A file, one connection per session: sessions sharing one connection
    # (StaticPool) undo each other's commits when they interleave.
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'analysis.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(PptBuilderBase.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    analysis_job.set_store_provider(lambda: SqlAnalysisStore(maker))
    analysis_job.clear_caches()
    yield maker
    analysis_job.clear_store_provider()
    analysis_job.clear_caches()
    await engine.dispose()
