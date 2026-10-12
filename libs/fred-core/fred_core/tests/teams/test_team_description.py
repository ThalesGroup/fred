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

"""A team's required description: the normalisation helper, the patch rule
and the database guarantee (SQLite, no Postgres needed)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fred_core.models.base import Base
from fred_core.sql.async_session import make_session_factory
from fred_core.teams.metadata_store import (
    TEAM_DESCRIPTION_PLACEHOLDER,
    TeamMetadataPatch,
    team_description_or_placeholder,
)
from fred_core.teams.team_metatada_models import TeamMetadataRow
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.parametrize("value", [None, "", "   ", "Ops", "x" * 19])
def test_missing_or_short_description_gets_the_placeholder(value: str | None) -> None:
    assert team_description_or_placeholder(value) == TEAM_DESCRIPTION_PLACEHOLDER


def test_valid_description_is_kept_trimmed() -> None:
    assert team_description_or_placeholder("x" * 20) == "x" * 20
    assert (
        team_description_or_placeholder("  Draft and review procurement contracts.  ")
        == "Draft and review procurement contracts."
    )


def test_long_description_is_cut_to_the_maximum() -> None:
    assert team_description_or_placeholder("x" * 501) == "x" * 500
    # A cut landing on whitespace is stripped again.
    assert team_description_or_placeholder("x" * 499 + " y") == "x" * 499


def test_placeholder_satisfies_its_own_bounds() -> None:
    assert team_description_or_placeholder(TEAM_DESCRIPTION_PLACEHOLDER) == (
        TEAM_DESCRIPTION_PLACEHOLDER
    )


@pytest.mark.parametrize("value", [None, "   ", "Too short"])
def test_patch_refuses_clearing_or_shortening(value: str | None) -> None:
    with pytest.raises(ValidationError):
        TeamMetadataPatch(description=value)


def test_patch_stores_a_trimmed_description_and_ignores_unset() -> None:
    patch = TeamMetadataPatch(description="  Answer internal IT questions.  ")
    assert patch.to_store_values() == {"description": "Answer internal IT questions."}
    assert "description" not in TeamMetadataPatch(name="Ops").to_store_values()


@pytest.mark.asyncio
@pytest.mark.parametrize("description", [None, "Short", "   padded short    "])
async def test_database_refuses_an_invalid_description(
    tmp_path: Path, description: str | None
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'desc.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sessions = make_session_factory(engine)
        with pytest.raises(IntegrityError):
            async with sessions() as s, s.begin():
                s.add(TeamMetadataRow(id="t1", name="Team", description=description))
    finally:
        await engine.dispose()
