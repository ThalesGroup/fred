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

"""Regression coverage for #2181: `GET /admin/capabilities` was firing up to 5
individual `lookup_subjects` (OpenFGA `ListUsers`) round-trips per row
(`enabled`/`disabled` team grants, `default_on`/`personal_on`/
`personal_disabled` org markers) — ~175 calls for the ~87-capability catalog.

Mirrors `test_teams_bulk_membership_call_count.py`'s shape for the equivalent
#2065/#2148 team-membership fan-out: a real, call-counting `RebacEngine`
(`CountingRebacEngine`, which raises if `lookup_subjects`/`ListUsers` is ever
called) proves the row build now uses exactly one exact
`list_direct_relations` `Read` per capability, cached with a 45s
write-invalidated TTL.

Also covers the performance-review correction on top of the first pass at this
fix: `has_org_relation` (and `_read_personal_scope`) ended up used ONLY by
write-path peek-before-mutate decisions once `_build_enablement_item` was
rewritten to fold its own single fetch locally — caching those would have
bought the read-only listing path nothing while risking a stale suspend/
revive/reject decision under concurrent multi-replica admin actions. They
deliberately bypass the cache (still `list_direct_relations`, never
`lookup_subjects` — cheaper per call even uncached).
"""

# pyright: reportArgumentType=false
# ^ this suite passes a minimal settings-store fake into `enable_capability_for_team`
#   on purpose (only `upsert` is ever called on this code path).
from __future__ import annotations

import time as time_module

import pytest
from _rebac_test_doubles import CountingRebacEngine
from control_plane_backend.capabilities import enablement
from control_plane_backend.capabilities.enablement import (
    cap_ref,
    enable_capability_for_team,
)
from control_plane_backend.capabilities.service import _build_enablement_item
from fred_core import ORGANIZATION_ID, RebacReference, Relation, RelationType, Resource
from fred_core.common import TeamId
from fred_sdk.contracts.capability import CapabilityCatalogEntry
from fred_sdk.contracts.capability.manifest import TeamScopePolicy


class _NullSettingsStore:
    async def upsert(self, *, team_id, capability_id, settings, updated_by):
        return None


def _entry(cap_id: str = "corp_drive") -> CapabilityCatalogEntry:
    return CapabilityCatalogEntry(
        id=cap_id,
        version="1.0.0",
        name=f"cap.{cap_id}.name",
        description=f"cap.{cap_id}.desc",
        icon="Icon",
        team_scope=TeamScopePolicy.ADMIN_GATED,
        team_settings_fields=[],
        kind="tool",
    )


def _seed_relations(cap_id: str) -> list[Relation]:
    resource = cap_ref(cap_id)
    return [
        Relation(
            subject=RebacReference(Resource.TEAM, "team-enabled"),
            relation=RelationType.ENABLED,
            resource=resource,
        ),
        Relation(
            subject=RebacReference(Resource.TEAM, "team-disabled"),
            relation=RelationType.DISABLED,
            resource=resource,
        ),
        Relation(
            subject=RebacReference(Resource.ORGANIZATION, ORGANIZATION_ID),
            relation=RelationType.DEFAULT_ON,
            resource=resource,
        ),
        Relation(
            subject=RebacReference(Resource.ORGANIZATION, ORGANIZATION_ID),
            relation=RelationType.PERSONAL_ON,
            resource=resource,
        ),
    ]


async def _build_item(engine: CountingRebacEngine, cap_id: str):
    return await _build_enablement_item(
        _entry(cap_id),
        rebac=engine,
        total_team_count=10,
        total_personal_space_count=5,
        impact={},
        reasoning_enabled_ids=frozenset(),
    )


@pytest.mark.asyncio
async def test_build_enablement_item_uses_one_read_never_list_users() -> None:
    """#2181: one row's ReBAC-derived fields must resolve from a SINGLE
    `list_direct_relations` Read — never `lookup_subjects` (`CountingRebacEngine`
    raises if it's called), regardless of how many distinct relations the row
    reports (`enabled`/`disabled`/`default_on`/`personal_on`)."""

    engine = CountingRebacEngine(direct_relations=_seed_relations("corp_drive"))

    item = await _build_item(engine, "corp_drive")

    assert len(engine.list_direct_relations_calls) == 1
    assert engine.list_direct_relations_calls[0][0] == cap_ref("corp_drive")
    assert engine.lookup_subjects_calls == 0
    assert item.default_on is True
    assert item.enabled_team_ids == ["team-enabled"]
    assert item.disabled_team_ids == ["team-disabled"]
    assert item.personal_scope == "enabled"


@pytest.mark.asyncio
async def test_build_enablement_item_serves_repeat_calls_from_cache() -> None:
    """#2181: within the 45s TTL, a second row build for the same capability
    must not re-hit OpenFGA."""

    engine = CountingRebacEngine(direct_relations=_seed_relations("corp_drive"))

    await _build_item(engine, "corp_drive")
    assert len(engine.list_direct_relations_calls) == 1

    await _build_item(engine, "corp_drive")
    assert len(engine.list_direct_relations_calls) == 1, (
        "second call within the TTL window must be served entirely from cache"
    )


@pytest.mark.asyncio
async def test_capability_relations_cache_refetches_after_ttl_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = CountingRebacEngine(direct_relations=_seed_relations("corp_drive"))

    fake_now = 1_000_000.0
    monkeypatch.setattr(time_module, "time", lambda: fake_now)

    await _build_item(engine, "corp_drive")
    assert len(engine.list_direct_relations_calls) == 1

    # still within the 45s TTL: cache hit, no new call
    fake_now += enablement._CAPABILITY_RELATIONS_CACHE_TTL_SECONDS - 1
    await _build_item(engine, "corp_drive")
    assert len(engine.list_direct_relations_calls) == 1

    # past the TTL: must be re-read
    fake_now += 2
    await _build_item(engine, "corp_drive")
    assert len(engine.list_direct_relations_calls) == 2


@pytest.mark.asyncio
async def test_enable_capability_for_team_invalidates_cache() -> None:
    """A grant must be visible on the very next read, not wait out the TTL —
    `enable_capability_for_team` calls `invalidate_capability_relations_cache`
    right after its write, mirroring the team-membership write paths."""

    engine = CountingRebacEngine()
    cap_id = "corp_drive"

    item_before = await _build_item(engine, cap_id)
    assert item_before.enabled_team_ids == []
    assert len(engine.list_direct_relations_calls) == 1

    await enable_capability_for_team(
        rebac=engine,
        settings_store=_NullSettingsStore(),
        catalog_entry=_entry(cap_id),
        team_id=TeamId("team-new"),
        settings={},
        updated_by="admin",
    )

    item_after = await _build_item(engine, cap_id)
    assert item_after.enabled_team_ids == ["team-new"]
    assert len(engine.list_direct_relations_calls) == 2, (
        "the write must have invalidated the cache entry for this capability"
    )


@pytest.mark.asyncio
async def test_has_org_relation_always_reads_fresh_never_cached() -> None:
    """`has_org_relation` (used by the write-path pre-checks in
    `reset_team_capability`/`set_personal_scope`) deliberately bypasses the
    cache — see its docstring: those are write-path peek-before-mutate
    decisions that must see live OpenFGA state, not up to 45s of another
    replica's stale write, and caching them would buy the read-only listing
    path nothing since it no longer calls this function at all. It still
    uses the cheaper `list_direct_relations` (`Read`) primitive rather than
    `lookup_subjects` (`ListUsers`) — just never caches the result."""

    engine = CountingRebacEngine(direct_relations=_seed_relations("corp_drive"))

    assert await enablement.has_org_relation(
        engine, "corp_drive", RelationType.DEFAULT_ON
    )
    assert await enablement.has_org_relation(
        engine, "corp_drive", RelationType.PERSONAL_ON
    )
    assert not await enablement.has_org_relation(
        engine, "corp_drive", RelationType.PERSONAL_DISABLED
    )
    assert len(engine.list_direct_relations_calls) == 3, (
        "has_org_relation must read fresh every call, never from the "
        "45s cache — it's a write-path correctness check now, and the "
        "listing endpoint no longer calls it"
    )
    assert engine.lookup_subjects_calls == 0


@pytest.mark.asyncio
async def test_has_org_relation_sees_a_write_immediately_on_the_same_pod() -> None:
    """The flip side of the above: because `has_org_relation` never caches,
    a write is visible on the very next call with no invalidation needed —
    proving the bypass is actually live, not just uncounted."""

    engine = CountingRebacEngine()
    cap_id = "corp_drive"

    assert not await enablement.has_org_relation(
        engine, cap_id, RelationType.DEFAULT_ON
    )

    await engine.add_relation(
        Relation(
            subject=RebacReference(Resource.ORGANIZATION, ORGANIZATION_ID),
            relation=RelationType.DEFAULT_ON,
            resource=cap_ref(cap_id),
        )
    )

    assert await enablement.has_org_relation(engine, cap_id, RelationType.DEFAULT_ON)
