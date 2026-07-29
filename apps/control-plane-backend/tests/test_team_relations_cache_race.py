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

"""PR #2160 review finding (Codex, P2): a `_get_team_relations_cached` call
that starts before a concurrent write's `invalidate_team_relations_cache`
but finishes after it would, without a guard, re-`set` the pre-write
snapshot it already had in hand — silently undoing the invalidation for a
full TTL. This file reproduces that interleaving deterministically (an
`asyncio.Event` gates the fake engine's `list_direct_relations` so the test
controls exactly when the "slow" read resumes relative to the write) and
proves the fix: the stale result is returned to its own caller but never
published back into the cache."""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from _rebac_test_doubles import CountingRebacEngine
from control_plane_backend.teams import service as teams_service
from fred_core import RebacReference, Relation, RelationType, Resource
from fred_core.common import TeamId


class _SlowRebacEngine(CountingRebacEngine):
    """`list_direct_relations` blocks on `gate` until the test releases it,
    so a read can be paused mid-flight while a concurrent write runs."""

    def __init__(self, *, gate: asyncio.Event, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._gate = gate

    async def list_direct_relations(
        self,
        resource: RebacReference,
        *,
        subject: RebacReference | None = None,
        consistency_token: str | None = None,
    ) -> list[Relation]:
        await self._gate.wait()
        return await super().list_direct_relations(
            resource, subject=subject, consistency_token=consistency_token
        )


@pytest.mark.asyncio
async def test_in_flight_read_invalidated_mid_flight_does_not_repopulate_cache() -> (
    None
):
    team_id = TeamId("team-race")
    gate = asyncio.Event()
    engine = _SlowRebacEngine(
        gate=gate,
        direct_relations=[
            Relation(
                subject=RebacReference(Resource.USER, "old-admin"),
                relation=RelationType.TEAM_ADMIN,
                resource=RebacReference(Resource.TEAM, team_id),
            )
        ],
    )

    # Start a read; it blocks inside `list_direct_relations` before it can
    # publish anything.
    read_task = asyncio.create_task(
        teams_service._get_team_relations_cached(engine, team_id)
    )
    await asyncio.sleep(0)

    # A concurrent write invalidates the team while that read is in flight —
    # nothing is cached yet, so this is a no-op on `_TEAM_RELATIONS_CACHE`
    # itself, but it must still be recorded so the in-flight read can notice.
    teams_service.invalidate_team_relations_cache(team_id)

    # Release the slow read: it resolves with the pre-write snapshot.
    gate.set()
    stale_result = await read_task
    assert {rel.subject.id for rel in cast(list[Relation], stale_result)} == {
        "old-admin"
    }

    # The race guard must have refused to publish that stale snapshot.
    assert team_id not in teams_service._TEAM_RELATIONS_CACHE

    # A subsequent read must hit OpenFGA again — not serve a clobbered entry.
    calls_before = len(engine.list_direct_relations_calls)
    await teams_service._get_team_relations_cached(engine, team_id)
    assert len(engine.list_direct_relations_calls) == calls_before + 1


@pytest.mark.asyncio
async def test_read_started_after_invalidation_caches_normally() -> None:
    """The guard must only reject reads that started *before* the
    invalidation — an ordinary read/write/read sequence with no overlap must
    still cache normally (no over-broad "never cache after any write" bug)."""
    team_id = TeamId("team-normal")
    gate = asyncio.Event()
    gate.set()  # never blocks in this test
    engine = _SlowRebacEngine(
        gate=gate,
        direct_relations=[
            Relation(
                subject=RebacReference(Resource.USER, "admin"),
                relation=RelationType.TEAM_ADMIN,
                resource=RebacReference(Resource.TEAM, team_id),
            )
        ],
    )

    await teams_service._get_team_relations_cached(engine, team_id)
    teams_service.invalidate_team_relations_cache(team_id)
    await teams_service._get_team_relations_cached(engine, team_id)

    assert team_id in teams_service._TEAM_RELATIONS_CACHE
    calls_before = len(engine.list_direct_relations_calls)
    await teams_service._get_team_relations_cached(engine, team_id)
    assert len(engine.list_direct_relations_calls) == calls_before, (
        "a read that starts after the last invalidation must still be cached"
    )
