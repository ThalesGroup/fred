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

"""
Per-team capability enablement — the write path (CAPAB-01 / #1980, RFC §8).

Covers the acceptance criteria that hold WITHOUT a live OpenFGA (the tri-state
`can_use` itself is exercised in fred-core's integration suite):
- settings validation against `team_settings_fields`;
- enable write ordering (settings row BEFORE the `enabled` tuple; a half-failure
  leaves it disabled, never enabled-without-settings);
- disable → suspension of dependent instances (`CAPABILITY_ACCESS_REVOKED`);
- default-on registration seeding + the `default_policy` flag;
- personal-space class scope (`personal_on`/`personal_disabled`, RFC §8.4).
"""

# pyright: reportArgumentType=false
# ^ this suite passes lightweight fakes (rebac / settings-store) and raw str
#   team ids into functions typed against the real protocols on purpose.
from __future__ import annotations

from typing import Any

import pytest
from control_plane_backend.capabilities import enablement, seeding
from control_plane_backend.capabilities.enablement import (
    AgentCapabilityDependencyNotSatisfied,
    CapabilitySettingsInvalid,
    DefaultOnNotAllowed,
    disable_capability_for_team,
    enable_capability_for_team,
    reset_capability_for_team,
    set_capability_personal_scope,
    suspend_dependent_instances,
    validate_team_settings,
)
from control_plane_backend.capabilities.settings_store import TeamCapabilitySettings
from control_plane_backend.product import service as product_service
from fred_core import CapabilityPermission, RebacDisabledResult
from fred_core.security.models import Resource
from fred_core.security.rebac.rebac_engine import (
    ORGANIZATION_ID,
    RebacReference,
    Relation,
    RelationType,
)
from fred_sdk.contracts.capability import CapabilityCatalogEntry
from fred_sdk.contracts.capability.manifest import TeamScopePolicy
from fred_sdk.contracts.models import FieldSpec
from test_main import _FakeAgentInstanceStore, _make_record

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeRebac:
    """Records the structural tuples written, and answers lookups off them."""

    def __init__(self, *, enabled: bool = True) -> None:
        self._enabled = enabled
        self.tuples: set[tuple[str, str, str]] = set()
        self.write_log: list[tuple[str, tuple[str, str, str]]] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _key(self, relation: Relation) -> tuple[str, str, str]:
        return (
            f"{relation.subject.type.value}:{relation.subject.id}",
            relation.relation.value,
            f"{relation.resource.type.value}:{relation.resource.id}",
        )

    async def add_relation(self, relation: Relation, **kwargs: object) -> str | None:
        key = self._key(relation)
        self.tuples.add(key)
        self.write_log.append(("add", key))
        return None

    async def delete_relation(self, relation: Relation) -> str | None:
        key = self._key(relation)
        self.tuples.discard(key)
        self.write_log.append(("delete", key))
        return None

    async def check_user_permission_or_raise(
        self, user, permission, resource_id, **kwargs
    ) -> None:
        """Permissive by default — the deny path has its own subclass."""
        return None

    async def lookup_subjects(self, resource, relation, subject_type):
        if not self._enabled:
            return RebacDisabledResult()
        obj = f"{resource.type.value}:{resource.id}"
        out = []
        for user, rel, o in self.tuples:
            if (
                o == obj
                and rel == relation.value
                and user.startswith(f"{subject_type.value}:")
            ):
                out.append(RebacReference(type=subject_type, id=user.split(":", 1)[1]))
        return out

    async def lookup_resources(
        self, subject, permission, resource_type, *, contextual_relations=None
    ):
        """Simplified `can_use` ListObjects for the `depends_on` gate tests
        (2026-07-19, GitHub #2004 item 5): `(enabled OR default_on) AND NOT
        disabled`, read straight off the recorded tuples — close enough to
        the real `capability#can_use` formula for these offline checks (the
        real tri-state is exercised in fred-core's OpenFGA integration suite)."""

        if not self._enabled:
            return RebacDisabledResult()
        team_key = f"{subject.type.value}:{subject.id}"
        org_key = f"organization:{ORGANIZATION_ID}"

        def _ids(user: str, rel: str) -> set[str]:
            return {
                o.split(":", 1)[1]
                for (u, r, o) in self.tuples
                if u == user and r == rel and o.startswith("capability:")
            }

        enabled_ids = _ids(team_key, "enabled")
        disabled_ids = _ids(team_key, "disabled")
        default_on_ids = _ids(org_key, "default_on")
        usable = (enabled_ids | default_on_ids) - disabled_ids
        return [RebacReference(type=resource_type, id=cid) for cid in usable]


# Real `template_capability_id` output (GitHub #2004 item 4: `agent__`
# namespace prefix) — derived, never hand-typed, so these tests can't drift
# from the id `is_template_capability_instance` actually computes.
SQL_EXPERT_TEMPLATE_ID = product_service.template_capability_id(
    "runtime-a", "sql_expert"
)


def _entry(
    cap_id: str = "corp_drive",
    *,
    team_scope: TeamScopePolicy = TeamScopePolicy.ADMIN_GATED,
    team_settings_fields: list[FieldSpec] | None = None,
    kind: str = "tool",
    default_capability_ids: tuple[str, ...] = (),
) -> CapabilityCatalogEntry:
    return CapabilityCatalogEntry(
        id=cap_id,
        version="1.0.0",
        name=f"cap.{cap_id}.name",
        description=f"cap.{cap_id}.desc",
        icon="Icon",
        team_scope=team_scope,
        team_settings_fields=team_settings_fields or [],
        kind=kind,
        default_capability_ids=default_capability_ids,
    )


class _FakeSettingsStore:
    def __init__(self, *, fail_upsert: bool = False) -> None:
        self._rows: dict[tuple[str, str], dict[str, Any]] = {}
        self._fail_upsert = fail_upsert

    async def upsert(self, *, team_id, capability_id, settings, updated_by):
        if self._fail_upsert:
            raise RuntimeError("settings row write failed")
        self._rows[(str(team_id), capability_id)] = dict(settings)
        return TeamCapabilitySettings(
            team_id=team_id,
            capability_id=capability_id,
            settings=dict(settings),
            updated_by=updated_by,
            updated_at=None,
        )

    async def get(self, *, team_id, capability_id):
        row = self._rows.get((str(team_id), capability_id))
        if row is None:
            return None
        return TeamCapabilitySettings(
            team_id=team_id,
            capability_id=capability_id,
            settings=row,
            updated_by=None,
            updated_at=None,
        )

    async def list_for_team(self, team_id):
        return {
            cap: settings
            for (tid, cap), settings in self._rows.items()
            if tid == str(team_id)
        }

    async def delete(self, *, team_id, capability_id):
        self._rows.pop((str(team_id), capability_id), None)


# ---------------------------------------------------------------------------
# validate_team_settings (AC3)
# ---------------------------------------------------------------------------


def test_validate_team_settings_rejects_unknown_key() -> None:
    fields = [FieldSpec(key="root_folder", type="string", title="Root")]
    with pytest.raises(CapabilitySettingsInvalid):
        validate_team_settings(fields, {"nope": "x"})


def test_validate_team_settings_requires_required_fields() -> None:
    fields = [FieldSpec(key="root_folder", type="string", title="Root", required=True)]
    with pytest.raises(CapabilitySettingsInvalid):
        validate_team_settings(fields, {})


def test_validate_team_settings_type_coherence_and_cleaning() -> None:
    fields = [
        FieldSpec(key="root_folder", type="string", title="Root", required=True),
        FieldSpec(key="verbose", type="boolean", title="Verbose"),
    ]
    with pytest.raises(CapabilitySettingsInvalid):
        validate_team_settings(fields, {"root_folder": 123})
    cleaned = validate_team_settings(
        fields, {"root_folder": "folder-123", "verbose": True}
    )
    assert cleaned == {"root_folder": "folder-123", "verbose": True}


# ---------------------------------------------------------------------------
# Enable write ordering (AC3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enable_writes_settings_row_before_enabled_tuple() -> None:
    rebac = _FakeRebac()
    settings = _FakeSettingsStore()
    entry = _entry(
        team_settings_fields=[FieldSpec(key="root_folder", type="string", title="R")]
    )

    await enable_capability_for_team(
        rebac=rebac,
        settings_store=settings,
        catalog_entry=entry,
        team_id="team-a",
        settings={"root_folder": "f-1"},
        updated_by="admin",
    )

    # Settings row present, enabled tuple present.
    assert (("team-a", "corp_drive")) in settings._rows
    assert ("team:team-a", "enabled", "capability:corp_drive") in rebac.tuples
    # Anchor written so can_manage/can_use resolve.
    assert (
        "organization:fred",
        "organization",
        "capability:corp_drive",
    ) in rebac.tuples


@pytest.mark.asyncio
async def test_enable_half_failure_leaves_capability_disabled() -> None:
    # Settings row write fails → the `enabled` tuple must NEVER be written.
    rebac = _FakeRebac()
    settings = _FakeSettingsStore(fail_upsert=True)
    entry = _entry()

    with pytest.raises(RuntimeError):
        await enable_capability_for_team(
            rebac=rebac,
            settings_store=settings,
            catalog_entry=entry,
            team_id="team-a",
            settings={},
            updated_by="admin",
        )
    assert ("team:team-a", "enabled", "capability:corp_drive") not in rebac.tuples


@pytest.mark.asyncio
async def test_enable_invalid_settings_writes_nothing() -> None:
    rebac = _FakeRebac()
    settings = _FakeSettingsStore()
    entry = _entry(
        team_settings_fields=[
            FieldSpec(key="root_folder", type="string", title="R", required=True)
        ]
    )
    with pytest.raises(CapabilitySettingsInvalid):
        await enable_capability_for_team(
            rebac=rebac,
            settings_store=settings,
            catalog_entry=entry,
            team_id="team-a",
            settings={},  # required root_folder missing
            updated_by="admin",
        )
    assert settings._rows == {}
    assert rebac.tuples == set()


# ---------------------------------------------------------------------------
# Disable → revocation → suspension (AC: the #1975 seam)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disable_suspends_dependent_instances_with_access_revoked() -> None:
    rebac = _FakeRebac()
    settings = _FakeSettingsStore()
    entry = _entry()
    # Grant first so there is an `enabled` tuple to revoke.
    await enable_capability_for_team(
        rebac=rebac,
        settings_store=settings,
        catalog_entry=entry,
        team_id="team-a",
        settings={},
        updated_by="admin",
    )
    dependent = _make_record(agent_instance_id="dep", team_id="team-a")
    dependent.tuning = dependent.tuning.model_copy(
        update={"selected_capability_ids": ["corp_drive"]}
    )
    unrelated = _make_record(agent_instance_id="other", team_id="team-a")
    unrelated.tuning = unrelated.tuning.model_copy(
        update={"selected_capability_ids": ["something_else"]}
    )
    store = _FakeAgentInstanceStore([dependent, unrelated])

    suspended = await disable_capability_for_team(
        rebac=rebac,
        settings_store=settings,
        agent_instance_store=store,
        catalog_entry=entry,
        team_id="team-a",
    )

    assert suspended == 1
    assert dependent.suspension_reason == "capability_access_revoked"
    # Instances that did not select the capability are untouched.
    assert unrelated.suspension_reason is None
    # `enabled` tuple gone, settings row KEPT (re-enable restores).
    assert ("team:team-a", "enabled", "capability:corp_drive") not in rebac.tuples
    assert ("team-a", "corp_drive") in settings._rows


@pytest.mark.asyncio
async def test_enable_capability_for_team_rejects_agent_capability_missing_tool_dependency() -> (
    None
):
    """2026-07-19, GitHub #2004 item 5 (`depends_on` fast-follow, fix A): an
    admin cannot grant a `kind="agent"` template to a team unless the team
    already `can_use` every id in the template's `default_capability_ids` —
    the exact live bug (SQL agent enabled for teams whose "Tabular data
    access" tool capability stayed disabled everywhere)."""

    rebac = _FakeRebac()
    settings = _FakeSettingsStore()
    sql_expert = _entry(
        SQL_EXPERT_TEMPLATE_ID,
        kind="agent",
        default_capability_ids=("mcp-knowledge-flow-mcp-tabular",),
    )

    with pytest.raises(AgentCapabilityDependencyNotSatisfied):
        await enable_capability_for_team(
            rebac=rebac,
            settings_store=settings,
            catalog_entry=sql_expert,
            team_id="team-a",
            settings={},
            updated_by="admin",
        )

    # Rejected before any write: no tuple, no settings row.
    assert rebac.tuples == set()
    assert ("team-a", SQL_EXPERT_TEMPLATE_ID) not in settings._rows


@pytest.mark.asyncio
async def test_enable_capability_for_team_allows_agent_capability_when_tool_dependency_usable() -> (
    None
):
    rebac = _FakeRebac()
    settings = _FakeSettingsStore()
    tool_entry = _entry("mcp-knowledge-flow-mcp-tabular")
    sql_expert = _entry(
        SQL_EXPERT_TEMPLATE_ID,
        kind="agent",
        default_capability_ids=("mcp-knowledge-flow-mcp-tabular",),
    )

    # Enable the dependency for the team FIRST.
    await enable_capability_for_team(
        rebac=rebac,
        settings_store=settings,
        catalog_entry=tool_entry,
        team_id="team-a",
        settings={},
        updated_by="admin",
    )
    # Now the agent capability grant succeeds.
    await enable_capability_for_team(
        rebac=rebac,
        settings_store=settings,
        catalog_entry=sql_expert,
        team_id="team-a",
        settings={},
        updated_by="admin",
    )

    assert (
        "team:team-a",
        "enabled",
        f"capability:{SQL_EXPERT_TEMPLATE_ID}",
    ) in rebac.tuples


@pytest.mark.asyncio
async def test_disable_agent_template_capability_suspends_its_instances() -> None:
    """2026-07-19, GitHub #2004 item 1: revoking a team's access to an agent
    TEMPLATE capability must suspend instances of that template — even though
    the template's own id is never in `selected_capability_ids` (only tool
    capabilities an instance activated live there)."""

    rebac = _FakeRebac()
    settings = _FakeSettingsStore()
    sql_expert = _entry(SQL_EXPERT_TEMPLATE_ID, kind="agent")
    await enable_capability_for_team(
        rebac=rebac,
        settings_store=settings,
        catalog_entry=sql_expert,
        team_id="team-a",
        settings={},
        updated_by="admin",
    )
    instance = _make_record(
        agent_instance_id="sql-1",
        team_id="team-a",
        source_runtime_id="runtime-a",
        source_agent_id="sql_expert",
    )
    unrelated = _make_record(
        agent_instance_id="other",
        team_id="team-a",
        source_runtime_id="runtime-a",
        source_agent_id="rags.sample.echo",
    )
    store = _FakeAgentInstanceStore([instance, unrelated])

    suspended = await disable_capability_for_team(
        rebac=rebac,
        settings_store=settings,
        agent_instance_store=store,
        catalog_entry=sql_expert,
        team_id="team-a",
    )

    assert suspended == 1
    assert instance.suspension_reason == "capability_access_revoked"
    assert unrelated.suspension_reason is None


@pytest.mark.asyncio
async def test_suspend_dependent_instances_is_idempotent_for_agent_template() -> None:
    """Re-running the revoke sweep must not double-count an instance already
    suspended for the same reason (mirrors the existing tool-capability
    idempotency guarantee in `reconcile_instance_suspension`)."""

    instance = _make_record(
        agent_instance_id="sql-1",
        team_id="team-a",
        source_runtime_id="runtime-a",
        source_agent_id="sql_expert",
    )
    store = _FakeAgentInstanceStore([instance])

    first = await suspend_dependent_instances(
        agent_instance_store=store,
        team_id="team-a",
        capability_id=SQL_EXPERT_TEMPLATE_ID,
    )
    second = await suspend_dependent_instances(
        agent_instance_store=store,
        team_id="team-a",
        capability_id=SQL_EXPERT_TEMPLATE_ID,
    )

    assert first == 1
    assert second == 0
    assert instance.suspension_reason == "capability_access_revoked"


@pytest.mark.asyncio
async def test_revive_dependent_instances_revives_agent_template_instance() -> None:
    """Symmetric counterpart of `test_disable_agent_template_capability_
    suspends_its_instances` (2026-07-19, GitHub #2004 item 2): an instance
    suspended by BEING an instance of a revoked `kind="agent"` template
    capability (condition 2, never `selected_capability_ids`) must be revived
    once the team can `can_use` the template again — the exact case every
    revive path (`revive_dependent_instances`, `set_default_on`,
    `set_capability_personal_scope`) previously never checked, leaving such
    instances suspended forever."""

    instance = _make_record(
        agent_instance_id="sql-1",
        team_id="team-a",
        source_runtime_id="runtime-a",
        source_agent_id="sql_expert",
    )
    store = _FakeAgentInstanceStore([instance])

    suspended = await suspend_dependent_instances(
        agent_instance_store=store,
        team_id="team-a",
        capability_id=SQL_EXPERT_TEMPLATE_ID,
    )
    assert suspended == 1
    assert instance.suspension_reason == "capability_access_revoked"

    revived = await enablement.revive_dependent_instances(
        agent_instance_store=store,
        capability_id=SQL_EXPERT_TEMPLATE_ID,
        usable_capability_ids={SQL_EXPERT_TEMPLATE_ID},
        available_by_source={"runtime-a": frozenset()},
        team_id="team-a",
    )

    assert revived == 1
    assert instance.suspension_reason is None


@pytest.mark.asyncio
async def test_revive_dependent_instances_keeps_agent_template_suspended_when_still_revoked() -> (
    None
):
    """The mirror of the case above: if the template capability is STILL not
    `can_use` for the team, the grant-side revive must not clear the
    suspension — same "a grant cannot fake it, it must check the real fact"
    rule `revive_dependent_instances` already applies to selected capabilities."""

    instance = _make_record(
        agent_instance_id="sql-1",
        team_id="team-a",
        source_runtime_id="runtime-a",
        source_agent_id="sql_expert",
    )
    instance.suspension_reason = "capability_access_revoked"
    store = _FakeAgentInstanceStore([instance])

    revived = await enablement.revive_dependent_instances(
        agent_instance_store=store,
        capability_id=SQL_EXPERT_TEMPLATE_ID,
        usable_capability_ids=set(),  # still not usable
        available_by_source={"runtime-a": frozenset()},
        team_id="team-a",
    )

    assert revived == 0
    assert instance.suspension_reason == "capability_access_revoked"


@pytest.mark.asyncio
async def test_personal_scope_enabled_rejects_agent_capability_missing_tool_dependency() -> (
    None
):
    """Personal-scope counterpart of fix A: class-enabling a `kind="agent"`
    template for every personal space is refused unless its default tool
    capabilities already have org-level personal access."""

    rebac = _FakeRebac()
    store = _FakeAgentInstanceStore([])
    sql_expert = _entry(
        SQL_EXPERT_TEMPLATE_ID,
        kind="agent",
        default_capability_ids=("mcp-knowledge-flow-mcp-tabular",),
    )

    with pytest.raises(AgentCapabilityDependencyNotSatisfied):
        await set_capability_personal_scope(
            rebac=rebac,
            agent_instance_store=store,
            catalog_entry=sql_expert,
            scope="enabled",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scope", [TeamScopePolicy.DEFAULT_ON, TeamScopePolicy.ADMIN_GATED]
)
async def test_disable_writes_optout_tuple_for_any_scope(
    scope: TeamScopePolicy,
) -> None:
    """Disable is the explicit tri-state position: the opt-out tuple is written
    regardless of scope, so it survives a later default-on flip and reads back
    as `disabled` in the admin matrix."""

    rebac = _FakeRebac()
    settings = _FakeSettingsStore()
    entry = _entry(team_scope=scope)
    store = _FakeAgentInstanceStore([])

    await disable_capability_for_team(
        rebac=rebac,
        settings_store=settings,
        agent_instance_store=store,
        catalog_entry=entry,
        team_id="team-a",
    )
    # Opt-out tuple written so the team truly loses `can_use`.
    assert ("team:team-a", "disabled", "capability:corp_drive") in rebac.tuples


# ---------------------------------------------------------------------------
# Reset to platform default (tri-state "default" segment)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_clears_both_tuples_and_keeps_settings() -> None:
    rebac = _FakeRebac()
    settings = _FakeSettingsStore()
    entry = _entry()
    store = _FakeAgentInstanceStore([])
    await enable_capability_for_team(
        rebac=rebac,
        settings_store=settings,
        catalog_entry=entry,
        team_id="team-a",
        settings={},
        updated_by="admin",
    )
    await disable_capability_for_team(
        rebac=rebac,
        settings_store=settings,
        agent_instance_store=store,
        catalog_entry=entry,
        team_id="team-a",
    )

    await reset_capability_for_team(
        rebac=rebac,
        agent_instance_store=store,
        catalog_entry=entry,
        team_id="team-a",
        default_on=True,
    )

    assert ("team:team-a", "enabled", "capability:corp_drive") not in rebac.tuples
    assert ("team:team-a", "disabled", "capability:corp_drive") not in rebac.tuples
    # Settings row kept — a later re-enable restores prior settings.
    assert ("team-a", "corp_drive") in settings._rows


@pytest.mark.asyncio
async def test_reset_suspends_dependents_when_default_is_off() -> None:
    """enabled → default with the platform default off means the team loses
    `can_use`, so the reset suspends dependents exactly like a disable."""

    rebac = _FakeRebac()
    settings = _FakeSettingsStore()
    entry = _entry()
    await enable_capability_for_team(
        rebac=rebac,
        settings_store=settings,
        catalog_entry=entry,
        team_id="team-a",
        settings={},
        updated_by="admin",
    )
    dependent = _make_record(agent_instance_id="dep", team_id="team-a")
    dependent.tuning = dependent.tuning.model_copy(
        update={"selected_capability_ids": ["corp_drive"]}
    )
    store = _FakeAgentInstanceStore([dependent])

    suspended = await reset_capability_for_team(
        rebac=rebac,
        agent_instance_store=store,
        catalog_entry=entry,
        team_id="team-a",
        default_on=False,
    )

    assert suspended == 1
    assert dependent.suspension_reason == "capability_access_revoked"


@pytest.mark.asyncio
async def test_reset_with_default_on_keeps_access_and_suspends_nothing() -> None:
    """enabled → default with default-on set: access continues by inheritance,
    so no dependent instance may be touched."""

    rebac = _FakeRebac()
    settings = _FakeSettingsStore()
    entry = _entry(team_scope=TeamScopePolicy.DEFAULT_ON)
    await enable_capability_for_team(
        rebac=rebac,
        settings_store=settings,
        catalog_entry=entry,
        team_id="team-a",
        settings={},
        updated_by="admin",
    )
    dependent = _make_record(agent_instance_id="dep", team_id="team-a")
    dependent.tuning = dependent.tuning.model_copy(
        update={"selected_capability_ids": ["corp_drive"]}
    )
    store = _FakeAgentInstanceStore([dependent])

    suspended = await reset_capability_for_team(
        rebac=rebac,
        agent_instance_store=store,
        catalog_entry=entry,
        team_id="team-a",
        default_on=True,
    )

    assert suspended == 0
    assert dependent.suspension_reason is None


# ---------------------------------------------------------------------------
# Registration seeding + default_policy flag (AC5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_seed_registration_writes_default_on_for_new_capability() -> None:
    rebac = _FakeRebac()
    catalog = [_entry("doc_access", team_scope=TeamScopePolicy.DEFAULT_ON)]

    seeded = await seeding.seed_registration_defaults(rebac=rebac, catalog=catalog)

    assert seeded == ["doc_access"]
    assert (
        "organization:fred",
        "default_on",
        "capability:doc_access",
    ) in rebac.tuples


@pytest.mark.asyncio
async def test_seed_registration_is_first_registration_only() -> None:
    rebac = _FakeRebac()
    entry = _entry("doc_access", team_scope=TeamScopePolicy.DEFAULT_ON)
    await seeding.seed_registration_defaults(rebac=rebac, catalog=[entry])
    # Simulate an admin toggling default_on OFF afterwards.
    await rebac.delete_relation(
        Relation(
            subject=RebacReference(type=Resource.ORGANIZATION, id=ORGANIZATION_ID),
            relation=RelationType.DEFAULT_ON,
            resource=RebacReference(type=Resource.CAPABILITY, id="doc_access"),
        )
    )
    # A second pass must NOT re-seed (the anchor already exists).
    seeded_again = await seeding.seed_registration_defaults(
        rebac=rebac, catalog=[entry]
    )
    assert seeded_again == []
    assert (
        "organization:fred",
        "default_on",
        "capability:doc_access",
    ) not in rebac.tuples


@pytest.mark.asyncio
async def test_seed_registration_explicit_policy_skips_all() -> None:
    rebac = _FakeRebac()
    catalog = [_entry("doc_access", team_scope=TeamScopePolicy.DEFAULT_ON)]
    seeded = await seeding.seed_registration_defaults(
        rebac=rebac, catalog=catalog, default_policy="explicit"
    )
    assert seeded == []
    assert rebac.tuples == set()


@pytest.mark.asyncio
async def test_seed_registration_skips_default_on_with_required_settings() -> None:
    rebac = _FakeRebac()
    catalog = [
        _entry(
            "corp_drive",
            team_scope=TeamScopePolicy.DEFAULT_ON,
            team_settings_fields=[
                FieldSpec(key="root_folder", type="string", title="R", required=True)
            ],
        )
    ]
    seeded = await seeding.seed_registration_defaults(rebac=rebac, catalog=catalog)
    assert seeded == []


@pytest.mark.asyncio
async def test_seed_registration_skips_admin_gated_mcp_entry() -> None:
    # #1988 regression: an MCP-derived catalog entry now carries a PLAIN server
    # id (no `mcp:` prefix, which was illegal in an OpenFGA object id and
    # crashed seeding). An admin-gated MCP server is seeded like any admin-gated
    # capability: NOT seeded, no anchor written — and crucially, no crash.
    rebac = _FakeRebac()
    catalog = [_entry("mcp-bank-core-demo", team_scope=TeamScopePolicy.ADMIN_GATED)]

    seeded = await seeding.seed_registration_defaults(rebac=rebac, catalog=catalog)

    assert seeded == []
    # No anchor / default_on tuple written for an admin-gated capability.
    assert rebac.tuples == set()


@pytest.mark.asyncio
async def test_seed_registration_seeds_default_on_mcp_entry() -> None:
    # #1988 regression: a DEFAULT_ON MCP-derived entry (plain server id) is
    # seeded exactly like any default-on capability — anchor + default_on tuple.
    rebac = _FakeRebac()
    catalog = [_entry("mcp-bank-core-demo", team_scope=TeamScopePolicy.DEFAULT_ON)]

    seeded = await seeding.seed_registration_defaults(rebac=rebac, catalog=catalog)

    assert seeded == ["mcp-bank-core-demo"]
    assert (
        "organization:fred",
        "default_on",
        "capability:mcp-bank-core-demo",
    ) in rebac.tuples


@pytest.mark.asyncio
async def test_seed_registration_isolates_per_entry_failure() -> None:
    # One bad entry (e.g. an id the FGA store rejects) must not starve the
    # rest of the catalog of their first-registration seed.
    class _RejectingRebac(_FakeRebac):
        async def add_relation(
            self, relation: Relation, **kwargs: object
        ) -> str | None:
            if relation.resource.id == "bad_cap":
                raise RuntimeError("HTTP 400 Invalid tuple")
            return await super().add_relation(relation, **kwargs)

    rebac = _RejectingRebac()
    catalog = [
        _entry("bad_cap", team_scope=TeamScopePolicy.DEFAULT_ON),
        _entry("good_cap", team_scope=TeamScopePolicy.DEFAULT_ON),
    ]

    seeded = await seeding.seed_registration_defaults(rebac=rebac, catalog=catalog)

    assert seeded == ["good_cap"]
    assert (
        "organization:fred",
        "default_on",
        "capability:good_cap",
    ) in rebac.tuples


# ---------------------------------------------------------------------------
# Catalog aggregation — invalid-id quarantine (#1988 hardening)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aggregation_quarantines_invalid_capability_ids(monkeypatch) -> None:
    # A pod on pre-#1988 code can advertise a legacy `mcp:`-prefixed id that
    # OpenFGA rejects in object ids. The aggregation chokepoint must drop it
    # (and keep valid entries) so no downstream FGA write ever sees it.
    from types import SimpleNamespace

    from control_plane_backend.capabilities.catalog import (
        aggregate_capability_catalog,
    )
    from control_plane_backend.product import service as product_service

    entries = [
        _entry("mcp:mcp-bank-core-demo"),
        _entry("doc_access"),
    ]

    async def _fake_fetch(base_url: str):
        return entries

    async def _fake_fetch_agents(base_url: str, runtime_id: str):
        return []

    monkeypatch.setattr(
        product_service, "_available_capabilities_for_source", _fake_fetch
    )
    monkeypatch.setattr(
        product_service, "_agent_capabilities_for_source", _fake_fetch_agents
    )
    deps = SimpleNamespace(
        configuration=SimpleNamespace(
            platform=SimpleNamespace(
                runtime_catalog_sources=[
                    SimpleNamespace(
                        enabled=True, base_url="http://pod", runtime_id="runtime-a"
                    )
                ]
            )
        )
    )

    catalog = await aggregate_capability_catalog(deps)

    assert set(catalog) == {"doc_access"}


@pytest.mark.asyncio
async def test_aggregation_unions_agent_kind_projections(monkeypatch) -> None:
    """
    CAPAB-01 (RFC §8.6): the admin catalog (`GET /admin/capabilities`) must
    list `kind="agent"` entries alongside `kind="tool"` ones — a SEPARATE
    fetch (`_agent_capabilities_for_source`), never merged into the runtime's
    own capability registry (see that function's docstring for why).
    """
    from types import SimpleNamespace

    from control_plane_backend.capabilities.catalog import (
        aggregate_capability_catalog,
    )
    from control_plane_backend.product import service as product_service

    async def _fake_fetch(base_url: str):
        return [_entry("doc_access")]

    async def _fake_fetch_agents(base_url: str, runtime_id: str):
        return [
            CapabilityCatalogEntry(
                id=product_service.template_capability_id(runtime_id, "sentinel"),
                version="1",
                name="agent.sentinel.name",
                description="agent.sentinel.description",
                icon="smart_toy",
                kind="agent",
                team_scope=TeamScopePolicy.ADMIN_GATED,
            )
        ]

    monkeypatch.setattr(
        product_service, "_available_capabilities_for_source", _fake_fetch
    )
    monkeypatch.setattr(
        product_service, "_agent_capabilities_for_source", _fake_fetch_agents
    )
    deps = SimpleNamespace(
        configuration=SimpleNamespace(
            platform=SimpleNamespace(
                runtime_catalog_sources=[
                    SimpleNamespace(
                        enabled=True, base_url="http://pod", runtime_id="runtime-a"
                    )
                ]
            )
        )
    )

    catalog = await aggregate_capability_catalog(deps)

    sentinel_id = product_service.template_capability_id("runtime-a", "sentinel")
    assert set(catalog) == {"doc_access", sentinel_id}
    assert catalog[sentinel_id].kind == "agent"
    assert catalog["doc_access"].kind == "tool"


@pytest.mark.asyncio
async def test_aggregation_refuses_tool_id_colliding_with_reserved_agent_namespace(
    monkeypatch,
) -> None:
    """2026-07-20, GitHub #2004 item 4: `AGENT_CAPABILITY_NAMESPACE_PREFIX`
    (`agent__`) is reserved exclusively for `kind="agent"` template
    projections. A `kind="tool"` entry that happens to land in that
    namespace (a coincidental MCP-server/tool id, or a future authoring bug)
    must be quarantined at the same chokepoint as an invalid-pattern id —
    never silently admitted to shadow (or be shadowed by) the real agent
    entry sharing that id."""

    from types import SimpleNamespace

    from control_plane_backend.capabilities.catalog import (
        aggregate_capability_catalog,
    )

    colliding_tool_id = product_service.template_capability_id(
        "runtime-a", "sql_expert"
    )

    async def _fake_fetch(base_url: str):
        return [_entry("doc_access"), _entry(colliding_tool_id, kind="tool")]

    async def _fake_fetch_agents(base_url: str, runtime_id: str):
        return [
            CapabilityCatalogEntry(
                id=colliding_tool_id,
                version="1",
                name="agent.sql_expert.name",
                description="agent.sql_expert.description",
                icon="smart_toy",
                kind="agent",
                team_scope=TeamScopePolicy.ADMIN_GATED,
            )
        ]

    monkeypatch.setattr(
        product_service, "_available_capabilities_for_source", _fake_fetch
    )
    monkeypatch.setattr(
        product_service, "_agent_capabilities_for_source", _fake_fetch_agents
    )
    deps = SimpleNamespace(
        configuration=SimpleNamespace(
            platform=SimpleNamespace(
                runtime_catalog_sources=[
                    SimpleNamespace(
                        enabled=True, base_url="http://pod", runtime_id="runtime-a"
                    )
                ]
            )
        )
    )

    catalog = await aggregate_capability_catalog(deps)

    # The tool entry is refused; the real agent entry (fetched second) wins
    # the id, never overwritten — the collision this prefix exists to prevent.
    assert set(catalog) == {"doc_access", colliding_tool_id}
    assert catalog[colliding_tool_id].kind == "agent"


@pytest.mark.asyncio
async def test_default_on_toggle_rejects_required_settings() -> None:
    rebac = _FakeRebac()
    store = _FakeAgentInstanceStore([])
    entry = _entry(
        team_settings_fields=[
            FieldSpec(key="root_folder", type="string", title="R", required=True)
        ]
    )
    with pytest.raises(DefaultOnNotAllowed):
        await enablement.set_capability_default_on(
            rebac=rebac, agent_instance_store=store, catalog_entry=entry, on=True
        )


# ---------------------------------------------------------------------------
# Personal-space class scope (RFC §8.4, #1961)
# ---------------------------------------------------------------------------

_PERSONAL_ON = "personal_on"
_PERSONAL_DISABLED = "personal_disabled"


def _org_tuple(relation: str, cap_id: str = "corp_drive") -> tuple[str, str, str]:
    return (f"organization:{ORGANIZATION_ID}", relation, f"capability:{cap_id}")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scope", "present", "absent"),
    [
        ("enabled", _PERSONAL_ON, _PERSONAL_DISABLED),
        ("disabled", _PERSONAL_DISABLED, _PERSONAL_ON),
    ],
)
async def test_personal_scope_writes_exactly_one_class_tuple(
    scope: str, present: str, absent: str
) -> None:
    rebac = _FakeRebac()
    store = _FakeAgentInstanceStore([])
    entry = _entry()

    await enablement.set_capability_personal_scope(
        rebac=rebac, agent_instance_store=store, catalog_entry=entry, scope=scope
    )

    assert _org_tuple(present) in rebac.tuples
    assert _org_tuple(absent) not in rebac.tuples
    # Anchored so can_manage/can_use resolve.
    assert _org_tuple("organization") in rebac.tuples


@pytest.mark.asyncio
async def test_personal_scope_default_clears_both_class_tuples() -> None:
    rebac = _FakeRebac()
    store = _FakeAgentInstanceStore([])
    entry = _entry()
    await enablement.set_capability_personal_scope(
        rebac=rebac, agent_instance_store=store, catalog_entry=entry, scope="enabled"
    )

    await enablement.set_capability_personal_scope(
        rebac=rebac, agent_instance_store=store, catalog_entry=entry, scope="default"
    )

    assert _org_tuple(_PERSONAL_ON) not in rebac.tuples
    assert _org_tuple(_PERSONAL_DISABLED) not in rebac.tuples


@pytest.mark.asyncio
async def test_personal_scope_is_idempotent() -> None:
    rebac = _FakeRebac()
    store = _FakeAgentInstanceStore([])
    entry = _entry()
    await enablement.set_capability_personal_scope(
        rebac=rebac, agent_instance_store=store, catalog_entry=entry, scope="enabled"
    )
    await enablement.set_capability_personal_scope(
        rebac=rebac, agent_instance_store=store, catalog_entry=entry, scope="enabled"
    )
    # Still exactly the grant tuple, no opt-out.
    assert _org_tuple(_PERSONAL_ON) in rebac.tuples
    assert _org_tuple(_PERSONAL_DISABLED) not in rebac.tuples


@pytest.mark.asyncio
async def test_personal_scope_enabled_rejects_required_settings() -> None:
    rebac = _FakeRebac()
    store = _FakeAgentInstanceStore([])
    entry = _entry(
        team_settings_fields=[
            FieldSpec(key="root_folder", type="string", title="R", required=True)
        ]
    )
    with pytest.raises(enablement.PersonalScopeNotAllowed):
        await enablement.set_capability_personal_scope(
            rebac=rebac,
            agent_instance_store=store,
            catalog_entry=entry,
            scope="enabled",
        )
    # disabled/default must still be allowed for the same capability.
    await enablement.set_capability_personal_scope(
        rebac=rebac, agent_instance_store=store, catalog_entry=entry, scope="disabled"
    )
    assert _org_tuple(_PERSONAL_DISABLED) in rebac.tuples


@pytest.mark.asyncio
async def test_personal_scope_off_suspends_only_personal_dependents() -> None:
    """enabled → disabled revokes the class grant: personal-space instances
    selecting the capability are suspended, but a regular team's instance and a
    personal instance whose team holds an explicit `enabled` grant are not."""

    rebac = _FakeRebac()
    store_seed = _FakeAgentInstanceStore([])
    entry = _entry()
    await enablement.set_capability_personal_scope(
        rebac=rebac,
        agent_instance_store=store_seed,
        catalog_entry=entry,
        scope="enabled",
    )
    # A personal team with an explicit `enabled` grant keeps access.
    await rebac.add_relation(
        Relation(
            subject=RebacReference(type=Resource.TEAM, id="personal-keep"),
            relation=RelationType.ENABLED,
            resource=RebacReference(type=Resource.CAPABILITY, id="corp_drive"),
        )
    )

    revoked = _make_record(agent_instance_id="p1", team_id="personal-u1")
    revoked.tuning = revoked.tuning.model_copy(
        update={"selected_capability_ids": ["corp_drive"]}
    )
    kept = _make_record(agent_instance_id="p2", team_id="personal-keep")
    kept.tuning = kept.tuning.model_copy(
        update={"selected_capability_ids": ["corp_drive"]}
    )
    regular = _make_record(agent_instance_id="r1", team_id="team-a")
    regular.tuning = regular.tuning.model_copy(
        update={"selected_capability_ids": ["corp_drive"]}
    )
    store = _FakeAgentInstanceStore([revoked, kept, regular])

    suspended = await enablement.set_capability_personal_scope(
        rebac=rebac, agent_instance_store=store, catalog_entry=entry, scope="disabled"
    )

    assert suspended == 1
    assert revoked.suspension_reason == "capability_access_revoked"
    # Explicit-grant personal team and the regular team are untouched.
    assert kept.suspension_reason is None
    assert regular.suspension_reason is None


@pytest.mark.asyncio
async def test_personal_scope_default_with_default_on_keeps_access() -> None:
    """enabled → default while the capability is default-on: personal spaces
    keep access by inheritance, so nothing is suspended."""

    rebac = _FakeRebac()
    store_seed = _FakeAgentInstanceStore([])
    entry = _entry(team_scope=TeamScopePolicy.DEFAULT_ON)
    # default-on marker + personal_on grant.
    await rebac.add_relation(
        Relation(
            subject=RebacReference(type=Resource.ORGANIZATION, id=ORGANIZATION_ID),
            relation=RelationType.DEFAULT_ON,
            resource=RebacReference(type=Resource.CAPABILITY, id="corp_drive"),
        )
    )
    await enablement.set_capability_personal_scope(
        rebac=rebac,
        agent_instance_store=store_seed,
        catalog_entry=entry,
        scope="enabled",
    )

    dependent = _make_record(agent_instance_id="p1", team_id="personal-u1")
    dependent.tuning = dependent.tuning.model_copy(
        update={"selected_capability_ids": ["corp_drive"]}
    )
    store = _FakeAgentInstanceStore([dependent])

    suspended = await enablement.set_capability_personal_scope(
        rebac=rebac, agent_instance_store=store, catalog_entry=entry, scope="default"
    )

    assert suspended == 0
    assert dependent.suspension_reason is None


@pytest.mark.asyncio
async def test_personal_scope_default_to_disabled_with_default_on_suspends() -> None:
    """default → disabled while default-on: the class opt-out subtracts the
    inherited access, so personal-space dependents are suspended."""

    rebac = _FakeRebac()
    entry = _entry(team_scope=TeamScopePolicy.DEFAULT_ON)
    await rebac.add_relation(
        Relation(
            subject=RebacReference(type=Resource.ORGANIZATION, id=ORGANIZATION_ID),
            relation=RelationType.DEFAULT_ON,
            resource=RebacReference(type=Resource.CAPABILITY, id="corp_drive"),
        )
    )
    dependent = _make_record(agent_instance_id="p1", team_id="personal-u1")
    dependent.tuning = dependent.tuning.model_copy(
        update={"selected_capability_ids": ["corp_drive"]}
    )
    store = _FakeAgentInstanceStore([dependent])

    suspended = await enablement.set_capability_personal_scope(
        rebac=rebac, agent_instance_store=store, catalog_entry=entry, scope="disabled"
    )

    assert suspended == 1
    assert dependent.suspension_reason == "capability_access_revoked"


# ---------------------------------------------------------------------------
# Personal-scope grant revive — the missing inverse of the suspend sweep above
# (#1975, mirrors `_revive_after_grant`/`set_default_on`'s revive in service.py)
# ---------------------------------------------------------------------------


def _availability_deps(
    monkeypatch: pytest.MonkeyPatch,
    store: "_FakeAgentInstanceStore",
    rebac: "_FakeRebac",
    *,
    available_by_source: dict,
    usable_ids: set[str] | None,
):
    """A `service.set_personal_scope`-shaped deps object with the live-fact
    fetches (`_available_capability_ids_by_source` / `usable_capability_ids`)
    stubbed the same way `test_capability_impact.py::_patch_availability`
    stubs them for the impact module."""

    from types import SimpleNamespace

    import control_plane_backend.capabilities.impact as impact_mod
    import control_plane_backend.product.service as product_service

    async def _fake_available(_deps):
        return available_by_source

    async def _fake_usable(_rebac, _team_id):
        return usable_ids

    monkeypatch.setattr(
        product_service, "_available_capability_ids_by_source", _fake_available
    )
    monkeypatch.setattr(impact_mod, "usable_capability_ids", _fake_usable)

    return SimpleNamespace(
        team_dependencies=SimpleNamespace(rebac=rebac),
        get_agent_instance_store=lambda: store,
        get_kpi_writer=lambda: None,
    )


@pytest.mark.asyncio
async def test_personal_scope_disabled_to_enabled_revives_suspended_dependents(
    monkeypatch,
) -> None:
    """disabled -> enabled must revive a personal-space agent suspended by the
    earlier access loss — the team/default-on grant paths already do this
    (`_revive_after_grant`); personal scope silently returned 0 instead. Fails
    on the old behavior, which never called any revive path for personal
    scope."""

    from types import SimpleNamespace

    from control_plane_backend.capabilities import service as capability_service

    rebac = _FakeRebac()
    entry = _entry()

    dependent = _make_record(agent_instance_id="p1", team_id="personal-u1")
    dependent.tuning = dependent.tuning.model_copy(
        update={"selected_capability_ids": ["corp_drive"]}
    )
    dependent.suspension_reason = "capability_access_revoked"
    store = _FakeAgentInstanceStore([dependent])

    async def _fake_catalog(_deps):
        return {"corp_drive": entry}

    monkeypatch.setattr(
        capability_service, "aggregate_capability_catalog", _fake_catalog
    )
    deps = _availability_deps(
        monkeypatch,
        store,
        rebac,
        available_by_source={"runtime-a": frozenset({"corp_drive"})},
        usable_ids={"corp_drive"},
    )

    result = await capability_service.set_personal_scope(
        user=SimpleNamespace(uid="admin"),
        capability_id="corp_drive",
        scope="enabled",
        deps=deps,
    )

    assert result.revived_instances == 1
    assert result.suspended_instances == 0
    assert dependent.suspension_reason is None


@pytest.mark.asyncio
async def test_personal_scope_disabled_to_enabled_revives_suspended_agent_template_dependent(
    monkeypatch,
) -> None:
    """Same disabled -> enabled revive, but for a personal-space instance
    suspended by BEING an instance of a `kind="agent"` template capability
    (condition 2) rather than by selecting it as a tool. Before GitHub #2004
    item 2, `_revive_personal_after_grant`'s team-gathering filter only ever
    checked `selected_capability_ids`, so this instance's team was never even
    considered a revive candidate and it stayed suspended forever."""

    from types import SimpleNamespace

    from control_plane_backend.capabilities import service as capability_service

    rebac = _FakeRebac()
    entry = _entry(SQL_EXPERT_TEMPLATE_ID, kind="agent")

    # The template's own id is never added to `selected_capability_ids` (only
    # tool capabilities an instance activated live there) — this instance
    # depends on it purely by being an instance of the template.
    dependent = _make_record(
        agent_instance_id="p1",
        team_id="personal-u1",
        source_runtime_id="runtime-a",
        source_agent_id="sql_expert",
    )
    dependent.suspension_reason = "capability_access_revoked"
    store = _FakeAgentInstanceStore([dependent])

    async def _fake_catalog(_deps):
        return {SQL_EXPERT_TEMPLATE_ID: entry}

    monkeypatch.setattr(
        capability_service, "aggregate_capability_catalog", _fake_catalog
    )
    deps = _availability_deps(
        monkeypatch,
        store,
        rebac,
        available_by_source={"runtime-a": frozenset()},
        usable_ids={SQL_EXPERT_TEMPLATE_ID},
    )

    result = await capability_service.set_personal_scope(
        user=SimpleNamespace(uid="admin"),
        capability_id=SQL_EXPERT_TEMPLATE_ID,
        scope="enabled",
        deps=deps,
    )

    assert result.revived_instances == 1
    assert result.suspended_instances == 0
    assert dependent.suspension_reason is None


@pytest.mark.asyncio
async def test_personal_scope_disabled_to_default_with_default_on_revives(
    monkeypatch,
) -> None:
    """disabled -> default while the capability is default-on ALSO grants
    personal-space access by inheritance, so it must revive exactly like
    disabled -> enabled."""

    from types import SimpleNamespace

    from control_plane_backend.capabilities import service as capability_service

    rebac = _FakeRebac()
    entry = _entry(team_scope=TeamScopePolicy.DEFAULT_ON)
    await rebac.add_relation(
        Relation(
            subject=RebacReference(type=Resource.ORGANIZATION, id=ORGANIZATION_ID),
            relation=RelationType.DEFAULT_ON,
            resource=RebacReference(type=Resource.CAPABILITY, id="corp_drive"),
        )
    )
    await rebac.add_relation(
        Relation(
            subject=RebacReference(type=Resource.ORGANIZATION, id=ORGANIZATION_ID),
            relation=RelationType.PERSONAL_DISABLED,
            resource=RebacReference(type=Resource.CAPABILITY, id="corp_drive"),
        )
    )

    dependent = _make_record(agent_instance_id="p1", team_id="personal-u1")
    dependent.tuning = dependent.tuning.model_copy(
        update={"selected_capability_ids": ["corp_drive"]}
    )
    dependent.suspension_reason = "capability_access_revoked"
    store = _FakeAgentInstanceStore([dependent])

    async def _fake_catalog(_deps):
        return {"corp_drive": entry}

    monkeypatch.setattr(
        capability_service, "aggregate_capability_catalog", _fake_catalog
    )
    deps = _availability_deps(
        monkeypatch,
        store,
        rebac,
        available_by_source={"runtime-a": frozenset({"corp_drive"})},
        usable_ids={"corp_drive"},
    )

    result = await capability_service.set_personal_scope(
        user=SimpleNamespace(uid="admin"),
        capability_id="corp_drive",
        scope="default",
        deps=deps,
    )

    assert result.revived_instances == 1
    assert dependent.suspension_reason is None


@pytest.mark.asyncio
async def test_personal_scope_revive_never_touches_config_invalid(
    monkeypatch,
) -> None:
    """A `capability_config_invalid` suspension is cleared only by a successful
    save (RFC §3.9) — the personal-scope grant revive must leave it alone even
    when personal-space access returns."""

    from types import SimpleNamespace

    from control_plane_backend.capabilities import service as capability_service

    rebac = _FakeRebac()
    entry = _entry()

    dependent = _make_record(agent_instance_id="p1", team_id="personal-u1")
    dependent.tuning = dependent.tuning.model_copy(
        update={"selected_capability_ids": ["corp_drive"]}
    )
    dependent.suspension_reason = "capability_config_invalid"
    store = _FakeAgentInstanceStore([dependent])

    async def _fake_catalog(_deps):
        return {"corp_drive": entry}

    monkeypatch.setattr(
        capability_service, "aggregate_capability_catalog", _fake_catalog
    )
    deps = _availability_deps(
        monkeypatch,
        store,
        rebac,
        available_by_source={"runtime-a": frozenset({"corp_drive"})},
        usable_ids={"corp_drive"},
    )

    result = await capability_service.set_personal_scope(
        user=SimpleNamespace(uid="admin"),
        capability_id="corp_drive",
        scope="enabled",
        deps=deps,
    )

    assert result.revived_instances == 0
    assert dependent.suspension_reason == "capability_config_invalid"


@pytest.mark.asyncio
async def test_personal_scope_revive_skips_unreachable_pod(monkeypatch) -> None:
    """An unreachable pod means UNKNOWN — the personal-scope grant revive must
    not clear a suspension it cannot prove is resolved."""

    from types import SimpleNamespace

    from control_plane_backend.capabilities import service as capability_service

    rebac = _FakeRebac()
    entry = _entry()

    dependent = _make_record(agent_instance_id="p1", team_id="personal-u1")
    dependent.tuning = dependent.tuning.model_copy(
        update={"selected_capability_ids": ["corp_drive"]}
    )
    dependent.suspension_reason = "capability_access_revoked"
    store = _FakeAgentInstanceStore([dependent])

    async def _fake_catalog(_deps):
        return {"corp_drive": entry}

    monkeypatch.setattr(
        capability_service, "aggregate_capability_catalog", _fake_catalog
    )
    deps = _availability_deps(
        monkeypatch,
        store,
        rebac,
        available_by_source={"runtime-a": None},  # pod unreachable
        usable_ids={"corp_drive"},
    )

    result = await capability_service.set_personal_scope(
        user=SimpleNamespace(uid="admin"),
        capability_id="corp_drive",
        scope="enabled",
        deps=deps,
    )

    assert result.revived_instances == 0
    assert dependent.suspension_reason == "capability_access_revoked"


@pytest.mark.asyncio
async def test_personal_scope_enabled_to_disabled_does_not_revive(
    monkeypatch,
) -> None:
    """A transition that only LOSES access (enabled -> disabled) must not
    report a revive — `had_access and not has_access` is the suspend path
    covered above, never the grant path."""

    from types import SimpleNamespace

    from control_plane_backend.capabilities import service as capability_service

    rebac = _FakeRebac()
    entry = _entry()
    await rebac.add_relation(
        Relation(
            subject=RebacReference(type=Resource.ORGANIZATION, id=ORGANIZATION_ID),
            relation=RelationType.PERSONAL_ON,
            resource=RebacReference(type=Resource.CAPABILITY, id="corp_drive"),
        )
    )

    dependent = _make_record(agent_instance_id="p1", team_id="personal-u1")
    dependent.tuning = dependent.tuning.model_copy(
        update={"selected_capability_ids": ["corp_drive"]}
    )
    store = _FakeAgentInstanceStore([dependent])

    async def _fake_catalog(_deps):
        return {"corp_drive": entry}

    monkeypatch.setattr(
        capability_service, "aggregate_capability_catalog", _fake_catalog
    )
    deps = _availability_deps(
        monkeypatch,
        store,
        rebac,
        available_by_source={"runtime-a": frozenset({"corp_drive"})},
        usable_ids={"corp_drive"},
    )

    result = await capability_service.set_personal_scope(
        user=SimpleNamespace(uid="admin"),
        capability_id="corp_drive",
        scope="disabled",
        deps=deps,
    )

    assert result.revived_instances == 0
    assert result.suspended_instances == 1
    assert dependent.suspension_reason == "capability_access_revoked"


@pytest.mark.asyncio
async def test_authz_injects_personal_team_edge_only_for_personal_teams() -> None:
    """A personal-space subject gets BOTH the `team` and `personal_team`
    contextual edges; a regular team gets only `team` (RFC §8.4)."""

    from control_plane_backend.capabilities.authz import _team_subject_and_context

    _, personal_ctx = _team_subject_and_context("personal-u1")
    relations = {r.relation.value for r in personal_ctx}
    assert relations == {"team", "personal_team"}

    _, regular_ctx = _team_subject_and_context("team-a")
    assert {r.relation.value for r in regular_ctx} == {"team"}


# ---------------------------------------------------------------------------
# can_use read-side helpers (AC2)
# ---------------------------------------------------------------------------


class _FilterRebac:
    """Answers `can_use` from a per-team allow-set (or disabled).

    Asserts the team-subject check shape: subject is `team:<id>` and the
    contextual `organization#team` reverse edge is supplied (the leak fix —
    a user subject would grant a capability in every team the user belongs to).
    """

    def __init__(self, usable_by_team: dict[str, set[str]] | None) -> None:
        self._usable_by_team = usable_by_team

    def _assert_team_check(self, subject, contextual_relations) -> str:
        assert subject.type is Resource.TEAM
        assert [
            (r.subject, r.relation.value, r.resource)
            for r in contextual_relations or []
        ] == [
            (
                subject,
                "team",
                RebacReference(type=Resource.ORGANIZATION, id=ORGANIZATION_ID),
            )
        ]
        return subject.id

    async def lookup_resources(
        self, subject, permission, resource_type, *, contextual_relations=None
    ):
        assert permission is CapabilityPermission.CAN_USE
        assert resource_type is Resource.CAPABILITY
        team_id = self._assert_team_check(subject, contextual_relations)
        if self._usable_by_team is None:
            return RebacDisabledResult()
        return [
            RebacReference(type=Resource.CAPABILITY, id=c)
            for c in self._usable_by_team.get(team_id, set())
        ]

    async def has_permission(
        self, subject, permission, resource, *, contextual_relations=None
    ):
        team_id = self._assert_team_check(subject, contextual_relations)
        if self._usable_by_team is None:
            return True
        return resource.id in self._usable_by_team.get(team_id, set())


@pytest.mark.asyncio
async def test_catalog_filter_gates_mcp_like_any_capability() -> None:
    # #1988: an MCP-backed capability's id is the plain catalog server id and is
    # FGA-gated exactly like any other capability — no `mcp:` pass-through.
    from control_plane_backend.capabilities.authz import (
        filter_entries_by_usable,
        usable_capability_ids,
    )

    rebac = _FilterRebac({"team-a": {"doc_access", "bank_core"}})
    usable = await usable_capability_ids(rebac, team_id="team-a")
    entries = [
        _entry("doc_access"),
        _entry("corp_drive"),
        CapabilityCatalogEntry(
            id="bank_core",
            version="1",
            name="n",
            description="d",
            icon="i",
        ),
        CapabilityCatalogEntry(
            id="market_data",  # MCP-backed, not usable → filtered out
            version="1",
            name="n",
            description="d",
            icon="i",
        ),
    ]
    kept = {e.id for e in filter_entries_by_usable(entries, usable)}
    assert kept == {"doc_access", "bank_core"}


@pytest.mark.asyncio
async def test_catalog_filter_disabled_rebac_keeps_everything() -> None:
    from control_plane_backend.capabilities.authz import (
        filter_entries_by_usable,
        usable_capability_ids,
    )

    rebac = _FilterRebac(None)
    usable = await usable_capability_ids(rebac, team_id="team-a")
    assert usable is None
    entries = [_entry("doc_access"), _entry("corp_drive")]
    assert len(filter_entries_by_usable(entries, usable)) == 2


@pytest.mark.asyncio
async def test_can_use_capability_check() -> None:
    from control_plane_backend.capabilities.authz import can_use_capability

    rebac = _FilterRebac({"team-a": {"doc_access", "bank_core"}})
    assert await can_use_capability(rebac, "team-a", "doc_access") is True
    assert await can_use_capability(rebac, "team-a", "corp_drive") is False
    # #1988: MCP-backed capabilities are gated like any other id — a granted
    # MCP capability passes, a non-granted one is rejected.
    assert await can_use_capability(rebac, "team-a", "bank_core") is True
    assert await can_use_capability(rebac, "team-a", "market_data") is False


@pytest.mark.asyncio
async def test_can_use_is_scoped_to_the_team_context() -> None:
    # The leak this fix closes: a capability enabled for team-a must NOT be
    # usable while operating in team-b, even when the SAME user belongs to
    # both teams (the check subject is the team, not the user).
    from control_plane_backend.capabilities.authz import (
        can_use_capability,
        usable_capability_ids,
    )

    rebac = _FilterRebac({"team-a": {"doc_access"}})
    assert await can_use_capability(rebac, "team-a", "doc_access") is True
    assert await can_use_capability(rebac, "team-b", "doc_access") is False
    assert await usable_capability_ids(rebac, team_id="team-b") == set()


# ---------------------------------------------------------------------------
# team_settings reach the runtime binding — restricted to selected caps (AC4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runtime_binding_carries_selected_team_settings() -> None:
    from types import SimpleNamespace

    import control_plane_backend.product.service as service

    record = _make_record(agent_instance_id="inst", team_id="team-a")
    record.tuning = record.tuning.model_copy(
        update={"selected_capability_ids": ["corp_drive"]}
    )
    instance_store = _FakeAgentInstanceStore([record])
    settings = _FakeSettingsStore()
    # One selected capability's settings + one UNselected capability's settings.
    await settings.upsert(
        team_id="team-a",
        capability_id="corp_drive",
        settings={"root_folder": "f-1"},
        updated_by="admin",
    )
    await settings.upsert(
        team_id="team-a",
        capability_id="other_cap",
        settings={"x": 1},
        updated_by="admin",
    )
    deps = SimpleNamespace(
        get_agent_instance_store=lambda: instance_store,
        get_team_capability_settings_store=lambda: settings,
    )

    binding = await service.get_runtime_binding_for_team("inst", "team-a", deps)  # type: ignore[arg-type]

    assert binding is not None
    # Only the SELECTED capability's settings are shipped to the pod.
    assert binding.team_capability_settings == {"corp_drive": {"root_folder": "f-1"}}


# ---------------------------------------------------------------------------
# API routes live + gated on can_manage (AC6)
# ---------------------------------------------------------------------------


@pytest.fixture()
def _use_test_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")


def test_admin_capability_routes_are_mounted(_use_test_configuration) -> None:
    from control_plane_backend.main import create_app

    app = create_app()
    paths = set(app.openapi().get("paths", {}))
    base = "/control-plane/v1"
    assert f"{base}/admin/capabilities" in paths
    assert f"{base}/admin/capabilities/{{capability_id}}/teams/{{team_id}}" in paths
    assert f"{base}/admin/capabilities/{{capability_id}}/default-on" in paths
    assert f"{base}/admin/capabilities/{{capability_id}}/personal-scope" in paths


@pytest.mark.asyncio
async def test_enablement_is_gated_on_can_manage() -> None:
    from types import SimpleNamespace

    from control_plane_backend.capabilities import service as capability_service
    from fred_core.security.models import AuthorizationError, Resource

    class _DenyingRebac(_FakeRebac):
        async def check_user_permission_or_raise(
            self, user, permission, resource_id, **kwargs
        ):
            raise AuthorizationError(
                "u", permission.value, Resource.CAPABILITY, "denied"
            )

    deps = SimpleNamespace(
        team_dependencies=SimpleNamespace(rebac=_DenyingRebac()),
    )
    with pytest.raises(AuthorizationError):
        await capability_service.enable_team_capability(
            user=SimpleNamespace(uid="u"),  # type: ignore[arg-type]
            capability_id="corp_drive",
            team_id="team-a",
            settings={},
            deps=deps,  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Aggregate list — enabled/disabled rosters and the platform team count (§8.5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aggregate_list_exposes_optouts_and_platform_team_count(
    monkeypatch,
) -> None:
    """The admin list must carry what the dashboard needs to state, exactly, how
    many teams can use a capability.

    For a default-on capability that means the `disabled` opt-out roster plus a
    PLATFORM-WIDE team count. The count must not come from `list_teams`, which is
    caller-scoped — an admin in 1 of 12 teams would otherwise see "1".
    """

    from types import SimpleNamespace

    from control_plane_backend.capabilities import service as capability_service

    rebac = _FakeRebac()
    cap = RebacReference(type=Resource.CAPABILITY, id="doc_access")
    org = RebacReference(type=Resource.ORGANIZATION, id=ORGANIZATION_ID)
    await rebac.add_relation(
        Relation(subject=org, relation=RelationType.DEFAULT_ON, resource=cap)
    )
    await rebac.add_relation(
        Relation(
            subject=RebacReference(type=Resource.TEAM, id="ops"),
            relation=RelationType.ENABLED,
            resource=cap,
        )
    )
    await rebac.add_relation(
        Relation(
            subject=RebacReference(type=Resource.TEAM, id="legal"),
            relation=RelationType.DISABLED,
            resource=cap,
        )
    )
    await rebac.add_relation(
        Relation(subject=org, relation=RelationType.PERSONAL_ON, resource=cap)
    )

    async def _fake_catalog(_deps):
        return {"doc_access": _entry("doc_access")}

    async def _fake_count(_team_deps):
        return 12

    async def _fake_personal_count(_team_deps):
        return 40

    monkeypatch.setattr(
        capability_service, "aggregate_capability_catalog", _fake_catalog
    )
    monkeypatch.setattr(
        capability_service, "count_all_collaborative_teams", _fake_count
    )
    monkeypatch.setattr(
        capability_service, "count_all_personal_spaces", _fake_personal_count
    )

    # No instances enrolled → the resting-health pass returns nothing and the
    # list still renders (an empty store short-circuits before any pod fetch).
    deps = SimpleNamespace(
        team_dependencies=SimpleNamespace(rebac=rebac),
        get_agent_instance_store=lambda: _FakeAgentInstanceStore([]),
    )
    result = await capability_service.list_capability_enablement(
        user=SimpleNamespace(uid="admin"),  # type: ignore[arg-type]
        deps=deps,  # type: ignore[arg-type]
    )

    item = result.items[0]
    assert item.default_on is True
    assert item.enabled_team_ids == ["ops"]
    assert item.disabled_team_ids == ["legal"]
    assert item.total_team_count == 12
    # 12 teams inherit it, 1 opted out → the dashboard renders 11.
    assert item.total_team_count - len(item.disabled_team_ids) == 11
    # The personal-space class grant is surfaced (RFC §8.4), with the
    # platform-wide personal-space denominator (= user count).
    assert item.personal_scope == "enabled"
    assert item.total_personal_space_count == 40
    # No enrolled instances → nothing broken, nothing unknown.
    assert item.suspended_instances == 0
    assert item.health_unknown_instances == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("relation", "expected"),
    [
        (None, "default"),
        (RelationType.PERSONAL_ON, "enabled"),
        (RelationType.PERSONAL_DISABLED, "disabled"),
    ],
)
async def test_aggregate_list_derives_personal_scope(
    monkeypatch, relation, expected
) -> None:
    from types import SimpleNamespace

    from control_plane_backend.capabilities import service as capability_service

    rebac = _FakeRebac()
    cap = RebacReference(type=Resource.CAPABILITY, id="doc_access")
    org = RebacReference(type=Resource.ORGANIZATION, id=ORGANIZATION_ID)
    if relation is not None:
        await rebac.add_relation(Relation(subject=org, relation=relation, resource=cap))

    async def _fake_catalog(_deps):
        return {"doc_access": _entry("doc_access")}

    async def _fake_count(_team_deps):
        return 3

    monkeypatch.setattr(
        capability_service, "aggregate_capability_catalog", _fake_catalog
    )
    monkeypatch.setattr(
        capability_service, "count_all_collaborative_teams", _fake_count
    )
    monkeypatch.setattr(capability_service, "count_all_personal_spaces", _fake_count)

    # No enrolled instances → the resting-health pass short-circuits before any
    # pod fetch (#1975).
    deps = SimpleNamespace(
        team_dependencies=SimpleNamespace(rebac=rebac),
        get_agent_instance_store=lambda: _FakeAgentInstanceStore([]),
    )
    result = await capability_service.list_capability_enablement(
        user=SimpleNamespace(uid="admin"),  # type: ignore[arg-type]
        deps=deps,  # type: ignore[arg-type]
    )
    assert result.items[0].personal_scope == expected
