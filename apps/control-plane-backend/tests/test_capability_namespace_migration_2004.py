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

"""GitHub #2004 item 4 — `kind="tool"`/`kind="agent"` capability-id namespace
separation (RFC `AGENT-CAPABILITY-RFC.md` §8.6, 2026-07-20 dated entry).

`template_capability_id` now reserves the `AGENT_CAPABILITY_NAMESPACE_PREFIX`
(`agent__`) exclusively for `kind="agent"` projections, so a `kind="tool"` id
can never again collide with one in the shared flat capability catalog
(`aggregate_capability_catalog` — collision-rejection tests live alongside
the rest of that aggregation suite in `test_capability_enablement_1980.py`).

This file covers the companion piece: `rename_agent_capability_ids_to_
namespaced_form`, the one-time migration that renames FGA tuples already
persisted under the pre-fix, un-prefixed id so the format change never
orphans a live grant.
"""

# pyright: reportArgumentType=false
# ^ this suite passes a lightweight `SimpleNamespace` deps double, and a fake
#   rebac, in place of the real typed protocols, on purpose (same convention
#   as test_capability_selection_1974.py / test_capability_enablement_1980.py).
from __future__ import annotations

from types import SimpleNamespace

import pytest
from control_plane_backend.config.models import RuntimeCatalogSourceConfig
from control_plane_backend.product import service
from fred_core.security.models import Resource
from fred_core.security.rebac.rebac_engine import (
    ORGANIZATION_ID,
    RebacReference,
    Relation,
    RelationType,
)
from fred_sdk.contracts.capability import CapabilityCatalogEntry
from fred_sdk.contracts.models import TeamScopePolicy

_ORG_REF = RebacReference(type=Resource.ORGANIZATION, id=ORGANIZATION_ID)


class _FakeMigrationRebac:
    """Tracks tuples as plain `(subject, relation, resource)` string triples
    and answers `has_direct_relation` straight off that set — enough to
    exercise a rename migration without a live OpenFGA."""

    def __init__(self) -> None:
        self.tuples: set[tuple[str, str, str]] = set()

    def _key(
        self, subject: RebacReference, relation: RelationType, resource: RebacReference
    ) -> tuple[str, str, str]:
        return (
            f"{subject.type.value}:{subject.id}",
            relation.value,
            f"{resource.type.value}:{resource.id}",
        )

    async def seed(
        self, subject: RebacReference, relation: RelationType, resource: RebacReference
    ) -> None:
        self.tuples.add(self._key(subject, relation, resource))

    async def has_direct_relation(
        self,
        subject: RebacReference,
        relation: RelationType,
        resource: RebacReference,
        *,
        consistency_token: str | None = None,
    ) -> bool:
        return self._key(subject, relation, resource) in self.tuples

    async def add_relation(self, relation: Relation, **kwargs: object) -> str | None:
        self.tuples.add(
            self._key(relation.subject, relation.relation, relation.resource)
        )
        return None

    async def delete_relation(self, relation: Relation) -> str | None:
        self.tuples.discard(
            self._key(relation.subject, relation.relation, relation.resource)
        )
        return None


class _FakeTeamMetadataStore:
    def __init__(self, team_ids: list[str]) -> None:
        self._teams = [SimpleNamespace(id=tid) for tid in team_ids]

    async def list_all(self):
        return self._teams


def _deps(
    rebac: _FakeMigrationRebac,
    team_ids: list[str],
    *,
    runtime_id: str = "runtime-a",
    unreachable: bool = False,
):
    return SimpleNamespace(
        team_dependencies=SimpleNamespace(
            rebac=rebac,
            get_team_metadata_store=lambda: _FakeTeamMetadataStore(team_ids),
        ),
        configuration=SimpleNamespace(
            platform=SimpleNamespace(
                runtime_catalog_sources=[
                    RuntimeCatalogSourceConfig(
                        runtime_id=runtime_id,
                        base_url=f"http://{runtime_id}/pod/v1",
                        enabled=not unreachable,
                    )
                ]
            )
        ),
    )


def _wire_agent_catalog(monkeypatch: pytest.MonkeyPatch, new_id: str) -> None:
    async def _fake_fetch_agents(base_url: str, runtime_id: str):
        return [
            CapabilityCatalogEntry(
                id=new_id,
                version="1",
                name="agent.sql_expert.name",
                description="agent.sql_expert.description",
                icon="smart_toy",
                kind="agent",
                team_scope=TeamScopePolicy.ADMIN_GATED,
            )
        ]

    monkeypatch.setattr(service, "_agent_capabilities_for_source", _fake_fetch_agents)


@pytest.mark.asyncio
async def test_rename_migration_moves_every_relation_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    new_id = service.template_capability_id("runtime-a", "sql_expert")
    old_id = new_id.removeprefix(service.AGENT_CAPABILITY_NAMESPACE_PREFIX)
    _wire_agent_catalog(monkeypatch, new_id)

    rebac = _FakeMigrationRebac()
    old_ref = RebacReference(type=Resource.CAPABILITY, id=old_id)
    team_a = RebacReference(type=Resource.TEAM, id="team-a")
    team_b = RebacReference(type=Resource.TEAM, id="team-b")
    await rebac.seed(_ORG_REF, RelationType.ORGANIZATION, old_ref)
    await rebac.seed(_ORG_REF, RelationType.DEFAULT_ON, old_ref)
    await rebac.seed(_ORG_REF, RelationType.PERSONAL_ON, old_ref)
    await rebac.seed(team_a, RelationType.ENABLED, old_ref)
    await rebac.seed(team_b, RelationType.DISABLED, old_ref)

    summary = await service.rename_agent_capability_ids_to_namespaced_form(
        _deps(rebac, ["team-a", "team-b"])
    )

    new_ref_key = f"capability:{new_id}"
    old_ref_key = f"capability:{old_id}"
    assert summary.templates_checked == 1
    assert summary.tuples_renamed == 5
    assert summary.skipped_unreachable_sources == 0
    # Every relation moved to the new id...
    assert (
        f"organization:{ORGANIZATION_ID}",
        "organization",
        new_ref_key,
    ) in rebac.tuples
    assert (
        f"organization:{ORGANIZATION_ID}",
        "default_on",
        new_ref_key,
    ) in rebac.tuples
    assert (
        f"organization:{ORGANIZATION_ID}",
        "personal_on",
        new_ref_key,
    ) in rebac.tuples
    assert ("team:team-a", "enabled", new_ref_key) in rebac.tuples
    assert ("team:team-b", "disabled", new_ref_key) in rebac.tuples
    # ...and nothing is left under the old id.
    assert not any(t[2] == old_ref_key for t in rebac.tuples)


@pytest.mark.asyncio
async def test_rename_migration_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    new_id = service.template_capability_id("runtime-a", "sql_expert")
    old_id = new_id.removeprefix(service.AGENT_CAPABILITY_NAMESPACE_PREFIX)
    _wire_agent_catalog(monkeypatch, new_id)

    rebac = _FakeMigrationRebac()
    old_ref = RebacReference(type=Resource.CAPABILITY, id=old_id)
    team_a = RebacReference(type=Resource.TEAM, id="team-a")
    await rebac.seed(team_a, RelationType.ENABLED, old_ref)

    deps = _deps(rebac, ["team-a"])
    first = await service.rename_agent_capability_ids_to_namespaced_form(deps)
    second = await service.rename_agent_capability_ids_to_namespaced_form(deps)

    assert first.tuples_renamed == 1
    assert second.tuples_renamed == 0
    assert ("team:team-a", "enabled", f"capability:{new_id}") in rebac.tuples


@pytest.mark.asyncio
async def test_rename_migration_dry_run_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    new_id = service.template_capability_id("runtime-a", "sql_expert")
    old_id = new_id.removeprefix(service.AGENT_CAPABILITY_NAMESPACE_PREFIX)
    _wire_agent_catalog(monkeypatch, new_id)

    rebac = _FakeMigrationRebac()
    old_ref = RebacReference(type=Resource.CAPABILITY, id=old_id)
    team_a = RebacReference(type=Resource.TEAM, id="team-a")
    await rebac.seed(team_a, RelationType.ENABLED, old_ref)

    summary = await service.rename_agent_capability_ids_to_namespaced_form(
        _deps(rebac, ["team-a"]), dry_run=True
    )

    assert summary.tuples_renamed == 1
    assert ("team:team-a", "enabled", f"capability:{old_id}") in rebac.tuples
    assert not any(t[2] == f"capability:{new_id}" for t in rebac.tuples)


@pytest.mark.asyncio
async def test_rename_migration_skips_unreachable_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _unreachable(base_url: str, runtime_id: str):
        return None

    monkeypatch.setattr(service, "_agent_capabilities_for_source", _unreachable)

    rebac = _FakeMigrationRebac()
    summary = await service.rename_agent_capability_ids_to_namespaced_form(
        _deps(rebac, [])
    )

    assert summary.templates_checked == 0
    assert summary.skipped_unreachable_sources == 1
    assert summary.tuples_renamed == 0
