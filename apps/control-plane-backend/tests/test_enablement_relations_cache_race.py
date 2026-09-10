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

"""The enablement relation cache's invalidation race, mirroring the team one.

The two caches share a guard shape, so they share these two cases: a read
overlapping an invalidation must not publish, and an ordinary read after an
invalidation must still cache.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from _rebac_test_doubles import CountingRebacEngine
from control_plane_backend.capabilities import enablement
from fred_core import RebacReference, Relation, RelationType, Resource

_CAPABILITY = RebacReference(Resource.CAPABILITY, "corp_drive")


class _SlowRebacEngine(CountingRebacEngine):
    """`list_direct_relations` blocks on `gate` so a read can be held mid-flight."""

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


def _engine(gate: asyncio.Event) -> _SlowRebacEngine:
    return _SlowRebacEngine(
        gate=gate,
        direct_relations=[
            Relation(
                subject=RebacReference(Resource.TEAM, "team-a"),
                relation=RelationType.ENABLED,
                resource=_CAPABILITY,
            )
        ],
    )


@pytest.mark.asyncio
async def test_in_flight_read_invalidated_mid_flight_does_not_repopulate_cache() -> (
    None
):
    gate = asyncio.Event()
    engine = _engine(gate)

    read_task = asyncio.create_task(
        enablement.get_enablement_relations_cached(engine, _CAPABILITY)
    )
    await asyncio.sleep(0)

    enablement.invalidate_enablement_relations_cache(_CAPABILITY)

    gate.set()
    await read_task

    assert enablement._CAPABILITY_RELATIONS_CACHE.get(_CAPABILITY) is None

    # The next read must reach the engine again rather than serve a clobbered entry.
    calls_before = len(engine.list_direct_relations_calls)
    await enablement.get_enablement_relations_cached(engine, _CAPABILITY)
    assert len(engine.list_direct_relations_calls) == calls_before + 1


@pytest.mark.asyncio
async def test_read_started_after_invalidation_caches_normally() -> None:
    """The guard must reject only reads that overlapped an invalidation.

    This is the case a wall-clock comparison got wrong: two readings taken a
    few statements apart are usually identical, so an ordinary sequential
    read/write/read silently declined to cache.
    """
    gate = asyncio.Event()
    gate.set()
    engine = _engine(gate)

    await enablement.get_enablement_relations_cached(engine, _CAPABILITY)
    enablement.invalidate_enablement_relations_cache(_CAPABILITY)
    await enablement.get_enablement_relations_cached(engine, _CAPABILITY)

    assert enablement._CAPABILITY_RELATIONS_CACHE.get(_CAPABILITY) is not None
    calls_before = len(engine.list_direct_relations_calls)
    await enablement.get_enablement_relations_cached(engine, _CAPABILITY)
    assert len(engine.list_direct_relations_calls) == calls_before, (
        "a read that starts after the last invalidation must still be cached"
    )


@pytest.mark.asyncio
async def test_repeated_write_then_read_cycles_always_cache() -> None:
    """The cache must populate under ordinary write/read traffic."""
    gate = asyncio.Event()
    gate.set()
    engine = _engine(gate)

    cached_after_cycle = []
    for _ in range(25):
        enablement.invalidate_enablement_relations_cache(_CAPABILITY)
        await enablement.get_enablement_relations_cached(engine, _CAPABILITY)
        cached_after_cycle.append(
            enablement._CAPABILITY_RELATIONS_CACHE.get(_CAPABILITY) is not None
        )

    assert all(cached_after_cycle), (
        f"only {sum(cached_after_cycle)}/25 non-overlapping reads were cached"
    )
