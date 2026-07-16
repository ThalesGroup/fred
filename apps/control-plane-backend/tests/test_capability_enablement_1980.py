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
- personal-space seeding.
"""

# pyright: reportArgumentType=false
# ^ this suite passes lightweight fakes (rebac / settings-store) and raw str
#   team ids into functions typed against the real protocols on purpose.
from __future__ import annotations

from typing import Any

import pytest
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

from control_plane_backend.capabilities import enablement, seeding
from control_plane_backend.capabilities.enablement import (
    CapabilitySettingsInvalid,
    DefaultOnNotAllowed,
    disable_capability_for_team,
    enable_capability_for_team,
    validate_team_settings,
)
from control_plane_backend.capabilities.settings_store import TeamCapabilitySettings
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

    async def add_relation(self, relation: Relation) -> str | None:
        key = self._key(relation)
        self.tuples.add(key)
        self.write_log.append(("add", key))
        return None

    async def delete_relation(self, relation: Relation) -> str | None:
        key = self._key(relation)
        self.tuples.discard(key)
        self.write_log.append(("delete", key))
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


def _entry(
    cap_id: str = "corp_drive",
    *,
    team_scope: TeamScopePolicy = TeamScopePolicy.ADMIN_GATED,
    team_settings_fields: list[FieldSpec] | None = None,
) -> CapabilityCatalogEntry:
    return CapabilityCatalogEntry(
        id=cap_id,
        version="1.0.0",
        name=f"cap.{cap_id}.name",
        description=f"cap.{cap_id}.desc",
        icon="Icon",
        team_scope=team_scope,
        team_settings_fields=team_settings_fields or [],
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
async def test_disable_default_on_writes_optout_tuple() -> None:
    rebac = _FakeRebac()
    settings = _FakeSettingsStore()
    entry = _entry(team_scope=TeamScopePolicy.DEFAULT_ON)
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
        async def add_relation(self, relation: Relation) -> str | None:
            if relation.resource.id == "bad_cap":
                raise RuntimeError("HTTP 400 Invalid tuple")
            return await super().add_relation(relation)

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

    monkeypatch.setattr(
        product_service, "_available_capabilities_for_source", _fake_fetch
    )
    deps = SimpleNamespace(
        configuration=SimpleNamespace(
            platform=SimpleNamespace(
                runtime_catalog_sources=[
                    SimpleNamespace(enabled=True, base_url="http://pod")
                ]
            )
        )
    )

    catalog = await aggregate_capability_catalog(deps)

    assert set(catalog) == {"doc_access"}


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
# Personal-space seeding (AC5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_personal_seeding_enables_and_is_idempotent() -> None:
    rebac = _FakeRebac()
    settings = _FakeSettingsStore()
    catalog = {"doc_access": _entry("doc_access")}

    seeded = await seeding.seed_personal_team_capabilities(
        rebac=rebac,
        settings_store=settings,
        catalog=catalog,
        personal_defaults=["doc_access"],
        team_id="personal-u1",
    )
    assert seeded == ["doc_access"]
    assert ("team:personal-u1", "enabled", "capability:doc_access") in rebac.tuples

    # Second pass: a settings row already exists → skip (no re-write).
    seeded_again = await seeding.seed_personal_team_capabilities(
        rebac=rebac,
        settings_store=settings,
        catalog=catalog,
        personal_defaults=["doc_access"],
        team_id="personal-u1",
    )
    assert seeded_again == []


@pytest.mark.asyncio
async def test_personal_seeding_skips_unknown_capability() -> None:
    rebac = _FakeRebac()
    settings = _FakeSettingsStore()
    seeded = await seeding.seed_personal_team_capabilities(
        rebac=rebac,
        settings_store=settings,
        catalog={},
        personal_defaults=["ghost"],
        team_id="personal-u1",
    )
    assert seeded == []


# ---------------------------------------------------------------------------
# can_use read-side helpers (AC2)
# ---------------------------------------------------------------------------


class _FilterRebac:
    """Answers `can_use` from an allow-set (or disabled)."""

    def __init__(self, usable: set[str] | None) -> None:
        self._usable = usable

    async def lookup_user_resources(self, user, permission):
        assert permission is CapabilityPermission.CAN_USE
        if self._usable is None:
            return RebacDisabledResult()
        return [RebacReference(type=Resource.CAPABILITY, id=c) for c in self._usable]

    async def has_user_permission(self, user, permission, resource_id):
        if self._usable is None:
            return True
        return resource_id in self._usable


@pytest.mark.asyncio
async def test_catalog_filter_gates_mcp_like_any_capability() -> None:
    # #1988: an MCP-backed capability's id is the plain catalog server id and is
    # FGA-gated exactly like any other capability — no `mcp:` pass-through.
    from control_plane_backend.capabilities.authz import (
        filter_entries_by_usable,
        usable_capability_ids,
    )

    rebac = _FilterRebac({"doc_access", "bank_core"})
    usable = await usable_capability_ids(rebac, user=object())
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
    usable = await usable_capability_ids(rebac, user=object())
    assert usable is None
    entries = [_entry("doc_access"), _entry("corp_drive")]
    assert len(filter_entries_by_usable(entries, usable)) == 2


@pytest.mark.asyncio
async def test_can_use_capability_check() -> None:
    from control_plane_backend.capabilities.authz import can_use_capability

    rebac = _FilterRebac({"doc_access", "bank_core"})
    assert await can_use_capability(rebac, object(), "doc_access") is True
    assert await can_use_capability(rebac, object(), "corp_drive") is False
    # #1988: MCP-backed capabilities are gated like any other id — a granted
    # MCP capability passes, a non-granted one is rejected.
    assert await can_use_capability(rebac, object(), "bank_core") is True
    assert await can_use_capability(rebac, object(), "market_data") is False


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


@pytest.mark.asyncio
async def test_enablement_is_gated_on_can_manage() -> None:
    from types import SimpleNamespace

    from fred_core.security.models import AuthorizationError, Resource
    from control_plane_backend.capabilities import service as capability_service

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
