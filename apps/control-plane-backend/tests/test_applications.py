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

"""Config-registered application catalog and V1 authorization contract."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, cast

import pytest
from control_plane_backend.app.dependencies import attach_application_container
from control_plane_backend.app.feature_flags import require_feature_enabled
from control_plane_backend.applications.api import router as applications_router
from control_plane_backend.applications.catalog import (
    ApplicationCatalog,
    ApplicationSourceConfig,
    ConfiguredApplicationCatalogSource,
)
from control_plane_backend.applications.service import list_team_applications
from control_plane_backend.capabilities import service as capability_service
from control_plane_backend.capabilities.api import router as capabilities_router
from control_plane_backend.capabilities.catalog import aggregate_capability_catalog
from control_plane_backend.capabilities.enablement import (
    ApplicationTeamScopeNotAllowed,
    CapabilityNotFound,
    PersonalScopeNotAllowed,
    disable_capability_for_team,
    enable_capability_for_team,
    reset_capability_for_team,
    set_capability_default_on,
    set_capability_personal_scope,
)
from control_plane_backend.capabilities.impact import CapabilityImpact
from control_plane_backend.capabilities.service import (
    _build_enablement_item,
    _require_can_manage,
)
from control_plane_backend.config.models import PlatformConfig
from control_plane_backend.product.dependencies import get_product_service_dependencies
from control_plane_backend.teams.schemas import TeamNotFoundError
from fastapi import FastAPI
from fred_core import (
    AuthorizationError,
    CapabilityPermission,
    KeycloakUser,
    get_current_user,
)
from fred_core.common import TeamId, personal_team_id
from fred_core.security.models import Resource
from fred_core.security.rebac.rebac_engine import (
    RebacDisabledResult,
    RebacReference,
    Relation,
    RelationType,
    TeamPermission,
)
from fred_core.teams.metadata_store import TeamMetadata
from fred_sdk.contracts.capability import CapabilityCatalogEntry, CapabilityManifest
from fred_sdk.contracts.capability.manifest import (
    APPLICATION_CAPABILITY_NAMESPACE_PREFIX,
    TeamScopePolicy,
)
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError


def _user(uid: str = "user-a") -> KeycloakUser:
    return KeycloakUser(uid=uid, username=uid, roles=[], email=None)


def _source(app_id: str, **overrides: Any) -> ApplicationSourceConfig:
    return ApplicationSourceConfig(
        **{
            "app_id": app_id,
            "ui_prefix": f"/apps/{app_id}",
            "version": "1.0.0",
            "icon": "extension",
            "display_name": {"en": app_id.title(), "fr": app_id.title()},
            "description": {"en": f"The {app_id} application."},
            **overrides,
        }
    )


def _feature_configuration(
    *,
    enable_applications: bool,
    application_sources: list[ApplicationSourceConfig] | None = None,
) -> Any:
    return SimpleNamespace(
        platform=SimpleNamespace(
            frontend=SimpleNamespace(
                feature_flags=SimpleNamespace(
                    enableApplications=enable_applications,
                )
            ),
            application_sources=(
                [_source("example")]
                if application_sources is None
                else application_sources
            ),
            runtime_catalog_sources=[],
        )
    )


def _catalog(*app_ids: str) -> ApplicationCatalog:
    return ApplicationCatalog(items=[_source(app_id) for app_id in app_ids])


@dataclass
class _CatalogSource:
    catalog: ApplicationCatalog
    events: list[str]

    def load(self) -> ApplicationCatalog:
        self.events.append("catalog")
        return self.catalog


class _MetadataStore:
    def __init__(self, events: list[str], *, exists: bool = True) -> None:
        self.events = events
        self.exists = exists

    async def get_by_team_id(self, team_id: TeamId) -> TeamMetadata | None:
        self.events.append("metadata")
        if not self.exists:
            return None
        return TeamMetadata(id=team_id, name=str(team_id))


class _DiscoveryRebac:
    def __init__(
        self,
        events: list[str],
        *,
        member: bool = True,
        usable: set[str] | None = None,
    ) -> None:
        self.events = events
        self.member = member
        self.usable = usable or set()
        self.lookup_subject: RebacReference | None = None
        self.lookup_context: tuple[Relation, ...] = ()

    async def check_user_team_permission_or_raise(
        self, user: KeycloakUser, permission: TeamPermission, team_id: str
    ) -> None:
        self.events.append("membership")
        assert permission is TeamPermission.CAN_USE_TEAM_APPLICATIONS
        if not self.member:
            raise AuthorizationError(user.uid, permission.value, Resource.TEAM)

    async def lookup_resources(
        self,
        subject: RebacReference,
        permission: CapabilityPermission,
        resource_type: Resource,
        *,
        contextual_relations: list[Relation] | None = None,
    ) -> list[RebacReference] | RebacDisabledResult:
        self.events.append("entitlements")
        assert permission is CapabilityPermission.CAN_USE
        assert resource_type is Resource.CAPABILITY
        self.lookup_subject = subject
        self.lookup_context = tuple(contextual_relations or ())
        return [
            RebacReference(Resource.CAPABILITY, capability_id)
            for capability_id in self.usable
        ]


class _DisabledDiscoveryRebac(_DiscoveryRebac):
    async def lookup_resources(
        self,
        subject: RebacReference,
        permission: CapabilityPermission,
        resource_type: Resource,
        *,
        contextual_relations: list[Relation] | None = None,
    ) -> RebacDisabledResult:
        self.events.append("entitlements")
        return RebacDisabledResult()


def _deps(rebac: object, metadata_store: _MetadataStore) -> Any:
    return cast(
        Any,
        type(
            "Deps",
            (),
            {
                "team_dependencies": type("TeamDeps", (), {"rebac": rebac})(),
                "get_team_metadata_store": lambda _self: metadata_store,
            },
        )(),
    )


@pytest.mark.asyncio
async def test_discovery_authorizes_before_team_or_application_metadata() -> None:
    events: list[str] = []
    rebac = _DiscoveryRebac(events, member=False)
    source = _CatalogSource(_catalog("example"), events)

    with pytest.raises(AuthorizationError):
        await list_team_applications(
            user=_user(),
            team_id=TeamId("team-a"),
            deps=_deps(rebac, _MetadataStore(events)),
            catalog_source=source,
        )

    assert events == ["membership"]


@pytest.mark.asyncio
async def test_discovery_filters_with_team_subject_capability_admission() -> None:
    events: list[str] = []
    rebac = _DiscoveryRebac(events, usable={"app__second"})

    result = await list_team_applications(
        user=_user(),
        team_id=TeamId("team-a"),
        deps=_deps(rebac, _MetadataStore(events)),
        catalog_source=_CatalogSource(_catalog("example", "second"), events),
    )

    assert events == ["membership", "metadata", "catalog", "entitlements"]
    assert [item.id for item in result.items] == ["second"]
    assert rebac.lookup_subject == RebacReference(Resource.TEAM, "team-a")
    assert rebac.lookup_context == (
        Relation(
            subject=RebacReference(Resource.TEAM, "team-a"),
            relation=RelationType.TEAM,
            resource=RebacReference(Resource.ORGANIZATION, "fred"),
        ),
    )


@pytest.mark.asyncio
async def test_discovery_returns_all_installed_apps_when_rebac_is_disabled() -> None:
    events: list[str] = []
    rebac = _DisabledDiscoveryRebac(events)

    result = await list_team_applications(
        user=_user(),
        team_id=TeamId("team-a"),
        deps=_deps(rebac, _MetadataStore(events)),
        catalog_source=_CatalogSource(_catalog("example", "second"), events),
    )

    assert [item.id for item in result.items] == ["example", "second"]
    assert events == ["membership", "metadata", "catalog", "entitlements"]


@pytest.mark.asyncio
async def test_personal_team_is_authorized_then_returns_empty_without_team_lookup() -> (
    None
):
    events: list[str] = []
    rebac = _DiscoveryRebac(events, usable={"app__example"})

    result = await list_team_applications(
        user=_user(),
        team_id=TeamId("personal"),
        deps=_deps(rebac, _MetadataStore(events)),
        catalog_source=_CatalogSource(_catalog("example"), events),
    )

    assert result.items == []
    # Authorization still runs first, and nothing downstream of it does: a
    # personal space reads neither the team registry nor the catalog.
    assert events == ["membership"]


@pytest.mark.asyncio
async def test_unknown_team_checks_membership_before_returning_not_found() -> None:
    events: list[str] = []
    rebac = _DiscoveryRebac(events)

    with pytest.raises(TeamNotFoundError):
        await list_team_applications(
            user=_user(),
            team_id=TeamId("missing"),
            deps=_deps(rebac, _MetadataStore(events, exists=False)),
            catalog_source=_CatalogSource(_catalog("example"), events),
        )

    assert events == ["membership", "metadata"]


def test_configured_source_serves_enabled_apps_and_projects_app_capability() -> None:
    source = ConfiguredApplicationCatalogSource(
        (_source("example"), _source("parked", enabled=False))
    )

    catalog = source.load()

    assert [item.app_id for item in catalog.items] == ["example"]
    entry = catalog.items[0].capability_entry()
    assert entry.kind == "app"
    assert entry.team_scope is TeamScopePolicy.ADMIN_GATED
    assert entry.id == f"{APPLICATION_CAPABILITY_NAMESPACE_PREFIX}example"


def test_summary_publishes_only_the_browser_facing_registration() -> None:
    summary = _source(
        "example",
        ui_prefix="https://apps.example.test/example/",
    ).summary()

    payload = summary.model_dump()
    assert payload == {
        "id": "example",
        "version": "1.0.0",
        "icon": "extension",
        "name": {"en": "Example", "fr": "Example"},
        "description": {"en": "The example application."},
        # A cross-origin UI prefix survives verbatim (bar the trailing slash):
        # moving an app to its own origin must stay a config edit.
        "ui_prefix": "https://apps.example.test/example",
    }


def test_unknown_feature_guard_name_fails_fast() -> None:
    with pytest.raises(ValueError, match="Unknown frontend feature flag"):
        require_feature_enabled("enableTypo")


@pytest.mark.asyncio
async def test_applications_flag_controls_capability_projection() -> None:
    disabled = SimpleNamespace(
        configuration=_feature_configuration(enable_applications=False)
    )
    enabled = SimpleNamespace(
        configuration=_feature_configuration(enable_applications=True)
    )

    assert await aggregate_capability_catalog(cast(Any, disabled)) == {}
    enabled_catalog = await aggregate_capability_catalog(cast(Any, enabled))
    assert set(enabled_catalog) == {"app__example"}


@pytest.mark.parametrize(
    "app_id",
    ["Example", "ex_ample", "-example", "example/../admin"],
)
def test_config_rejects_malformed_application_id(app_id: str) -> None:
    with pytest.raises(ValidationError):
        _source(app_id)


@pytest.mark.parametrize(
    "ui_prefix",
    [
        "//attacker.test/example",
        "javascript:alert(1)",
        "/apps/../admin",
        "/apps/ex ample",
        "ftp://example.test/example",
        "apps/example",
    ],
)
def test_config_rejects_unsafe_ui_prefix(ui_prefix: str) -> None:
    with pytest.raises(ValidationError):
        _source("example", ui_prefix=ui_prefix)


# The gateway keys its upstream map on the URI segment after /apps/, so a
# same-origin prefix that disagrees with its own app_id routes nowhere. Both
# halves can be spelled identically and still 404, which is why this is
# rejected here rather than left to a cross-config check.
@pytest.mark.parametrize(
    "ui_prefix",
    ["/apps/exampl", "/apps/example/extra", "/example", "/apps", "/"],
)
def test_config_rejects_own_origin_ui_prefix_that_is_not_its_own_route(
    ui_prefix: str,
) -> None:
    with pytest.raises(ValidationError, match="/apps/example"):
        _source("example", ui_prefix=ui_prefix)


def test_config_accepts_the_own_route_and_any_safe_foreign_origin() -> None:
    assert _source("example", ui_prefix="/apps/example").ui_prefix == "/apps/example"
    # Trailing slash is normalized away before the comparison, not rejected.
    assert _source("example", ui_prefix="/apps/example/").ui_prefix == "/apps/example"
    # The cross-origin escape stays unconstrained: moving an application to
    # its own origin must remain a configuration edit.
    assert (
        _source("example", ui_prefix="https://apps.example.test/anything").ui_prefix
        == "https://apps.example.test/anything"
    )


# Proxy upstreams belong to the frontend gateway, which is the only process
# that routes to them. Accepting them here too would be a second declaration
# nothing reads, held to a weaker rule than the gateway's own.
@pytest.mark.parametrize("field", ["service_upstream", "service_required"])
def test_config_refuses_to_carry_gateway_only_registration(field: str) -> None:
    with pytest.raises(ValidationError, match="extra"):
        _source("example", **{field: "http://example-service:8000"})


def test_config_rejects_duplicate_application_ids() -> None:
    with pytest.raises(ValidationError, match="Duplicate application_sources app_id"):
        PlatformConfig(application_sources=[_source("example"), _source("example")])


def test_config_requires_an_english_display_string() -> None:
    with pytest.raises(ValidationError, match="'en' entry"):
        _source("example", display_name={"fr": "Exemple"})


def test_config_accepts_material_icon_and_rejects_unsafe_icon() -> None:
    assert _source("example", icon="architecture").icon == "architecture"

    with pytest.raises(ValidationError):
        _source("example", icon="../architecture")


def test_app_is_wire_only_not_runtime_manifest_kind() -> None:
    catalog_entry = CapabilityCatalogEntry(
        id="app__example",
        version="1.0.0",
        name="applications.example.name",
        description="applications.example.description",
        icon="extension",
        kind="app",
    )
    assert catalog_entry.kind == "app"

    with pytest.raises(ValidationError):
        CapabilityManifest(
            id="app__example",
            version="1.0.0",
            name="applications.example.name",
            description="applications.example.description",
            icon="extension",
            kind=cast(Any, "app"),
        )


class _TupleRebac:
    def __init__(self) -> None:
        self.relations: set[Relation] = set()

    async def add_relation(self, relation: Relation, **_kwargs: object) -> None:
        self.relations.add(relation)

    async def delete_relation(self, relation: Relation) -> None:
        self.relations.discard(relation)

    async def check_user_permission_or_raise(self, *_args: object) -> None:
        return None

    async def list_direct_relations(
        self, _resource: RebacReference, **_kwargs: object
    ) -> list[Relation]:
        return list(self.relations)


class _LifecycleRebac(_TupleRebac):
    async def check_user_team_permission_or_raise(
        self,
        _user: KeycloakUser,
        permission: TeamPermission,
        team_id: str,
    ) -> None:
        assert permission is TeamPermission.CAN_USE_TEAM_APPLICATIONS
        assert team_id == "team-a"

    async def lookup_resources(
        self,
        subject: RebacReference,
        permission: CapabilityPermission,
        resource_type: Resource,
        **_kwargs: object,
    ) -> list[RebacReference]:
        assert permission is CapabilityPermission.CAN_USE
        assert resource_type is Resource.CAPABILITY
        return [
            relation.resource
            for relation in self.relations
            if relation.subject == subject
            and relation.relation is RelationType.ENABLED
            and relation.resource.type is resource_type
        ]


def _relation_snapshot(relations: set[Relation]) -> bytes:
    rows = sorted(
        (
            relation.subject.type.value,
            relation.subject.id,
            relation.relation.value,
            relation.resource.type.value,
            relation.resource.id,
        )
        for relation in relations
    )
    return b"\n".join("\0".join(row).encode() for row in rows)


def _app_entry() -> CapabilityCatalogEntry:
    return _catalog("example").items[0].capability_entry()


@pytest.mark.asyncio
async def test_unknown_app_id_is_rejected_before_structural_anchor_write() -> None:
    rebac = _TupleRebac()
    deps = SimpleNamespace(
        configuration=_feature_configuration(enable_applications=True)
    )

    with pytest.raises(CapabilityNotFound):
        await _require_can_manage(
            cast(Any, rebac), _user(), "app__typo", deps=cast(Any, deps)
        )

    assert rebac.relations == set()


@pytest.mark.asyncio
async def test_disabled_app_is_rejected_before_structural_anchor_write() -> None:
    rebac = _TupleRebac()
    deps = SimpleNamespace(
        configuration=_feature_configuration(enable_applications=False)
    )

    with pytest.raises(CapabilityNotFound):
        await _require_can_manage(
            cast(Any, rebac), _user(), "app__example", deps=cast(Any, deps)
        )

    assert rebac.relations == set()


@pytest.mark.asyncio
async def test_applications_flag_preserves_existing_grant_across_off_on() -> None:
    configuration = _feature_configuration(enable_applications=False)
    rebac = _LifecycleRebac()
    grant = Relation(
        subject=RebacReference(Resource.TEAM, "team-a"),
        relation=RelationType.ENABLED,
        resource=RebacReference(Resource.CAPABILITY, "app__example"),
    )
    rebac.relations.add(grant)
    relation_bytes = _relation_snapshot(rebac.relations)
    deps = SimpleNamespace(
        configuration=configuration,
        team_dependencies=SimpleNamespace(rebac=rebac),
        get_team_metadata_store=lambda: _MetadataStore([]),
    )

    app = FastAPI()
    attach_application_container(
        app,
        cast(Any, SimpleNamespace(configuration=configuration)),
    )
    app.include_router(applications_router, prefix="/control-plane/v1")
    app.include_router(capabilities_router, prefix="/control-plane/v1")
    app.dependency_overrides[get_product_service_dependencies] = lambda: deps
    app.dependency_overrides[get_current_user] = _user

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        hidden = await client.get("/control-plane/v1/teams/team-a/applications")
        blocked_mutation = await client.put(
            "/control-plane/v1/admin/capabilities/app__example/teams/team-a",
            json={"settings": {}},
        )

        assert hidden.status_code == 404
        assert blocked_mutation.status_code == 404
        assert _relation_snapshot(rebac.relations) == relation_bytes
        assert next(iter(rebac.relations)) is grant

        configuration.platform.frontend.feature_flags.enableApplications = True
        visible = await client.get("/control-plane/v1/teams/team-a/applications")

    assert visible.status_code == 200
    assert [item["id"] for item in visible.json()["items"]] == ["example"]
    assert _relation_snapshot(rebac.relations) == relation_bytes
    assert next(iter(rebac.relations)) is grant


@pytest.mark.asyncio
async def test_admin_app_row_forces_agent_impact_and_reasoning_fields_empty() -> None:
    rebac = _TupleRebac()
    entry = _app_entry()
    rebac.relations.update(
        {
            Relation(
                subject=RebacReference(Resource.TEAM, team_id),
                relation=RelationType.ENABLED,
                resource=RebacReference(Resource.CAPABILITY, entry.id),
            )
            for team_id in ("team-a", "personal", "personal-user-a")
        }
    )

    item = await _build_enablement_item(
        entry,
        rebac=cast(Any, rebac),
        total_team_count=3,
        total_personal_space_count=2,
        impact={
            entry.id: CapabilityImpact(
                suspended_instances=7,
                skipped_unreachable=5,
            )
        },
        reasoning_enabled_ids=frozenset({entry.id}),
    )

    assert item.suspended_instances == 0
    assert item.health_unknown_instances == 0
    assert item.suspended_instance_details == []
    assert item.thinking_profile_ids == []
    assert item.reasoning_enabled is False
    assert item.total_personal_space_count == 0
    assert item.enabled_team_ids == ["team-a"]


@pytest.mark.asyncio
async def test_app_enablement_writes_only_entitlement_and_skips_agent_stores() -> None:
    rebac = _TupleRebac()
    validated = await enable_capability_for_team(
        rebac=cast(Any, rebac),
        settings_store=None,
        catalog_entry=_app_entry(),
        team_id=TeamId("team-a"),
        settings={},
        updated_by="admin",
    )

    assert validated == {}
    assert any(
        relation.relation is RelationType.ENABLED
        and relation.subject == RebacReference(Resource.TEAM, "team-a")
        for relation in rebac.relations
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("team_id", [TeamId("personal"), personal_team_id("user-a")])
async def test_app_enable_rejects_personal_team_forms_before_writes(
    team_id: TeamId,
) -> None:
    rebac = _TupleRebac()

    with pytest.raises(ApplicationTeamScopeNotAllowed):
        await enable_capability_for_team(
            rebac=cast(Any, rebac),
            settings_store=None,
            catalog_entry=_app_entry(),
            team_id=team_id,
            settings={},
            updated_by="admin",
        )

    assert rebac.relations == set()


@pytest.mark.asyncio
async def test_app_personal_tuple_cleanup_remains_available() -> None:
    rebac = _TupleRebac()
    app = _app_entry()
    team_id = personal_team_id("user-a")
    enabled = Relation(
        subject=RebacReference(Resource.TEAM, str(team_id)),
        relation=RelationType.ENABLED,
        resource=RebacReference(Resource.CAPABILITY, app.id),
    )
    rebac.relations.add(enabled)

    assert (
        await disable_capability_for_team(
            rebac=cast(Any, rebac),
            settings_store=None,
            agent_instance_store=None,
            catalog_entry=app,
            team_id=team_id,
        )
        == 0
    )
    assert enabled not in rebac.relations

    assert (
        await reset_capability_for_team(
            rebac=cast(Any, rebac),
            agent_instance_store=None,
            catalog_entry=app,
            team_id=team_id,
            default_on=False,
        )
        == 0
    )
    with pytest.raises(ApplicationTeamScopeNotAllowed):
        await reset_capability_for_team(
            rebac=cast(Any, rebac),
            agent_instance_store=None,
            catalog_entry=app,
            team_id=team_id,
            default_on=True,
        )


@pytest.mark.asyncio
async def test_app_disable_canonicalizes_personal_alias_for_legacy_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rebac = _TupleRebac()
    app = _app_entry()
    canonical_team_id = personal_team_id("user-a")
    enabled = Relation(
        subject=RebacReference(Resource.TEAM, str(canonical_team_id)),
        relation=RelationType.ENABLED,
        resource=RebacReference(Resource.CAPABILITY, app.id),
    )
    rebac.relations.add(enabled)

    async def _catalog(_deps: object) -> dict[str, CapabilityCatalogEntry]:
        return {app.id: app}

    monkeypatch.setattr(
        capability_service,
        "aggregate_capability_catalog",
        _catalog,
    )
    deps = cast(
        Any,
        SimpleNamespace(
            configuration=_feature_configuration(enable_applications=True),
            team_dependencies=SimpleNamespace(rebac=rebac),
            get_kpi_writer=lambda: None,
        ),
    )

    result = await capability_service.disable_team_capability(
        user=_user(),
        capability_id=app.id,
        team_id=TeamId("personal"),
        deps=deps,
    )

    assert enabled not in rebac.relations
    assert result.team_id == str(canonical_team_id)


@pytest.mark.asyncio
async def test_app_default_off_and_personal_scope_never_touch_agent_store() -> None:
    rebac = _TupleRebac()
    assert (
        await set_capability_default_on(
            rebac=cast(Any, rebac),
            agent_instance_store=None,
            catalog_entry=_app_entry(),
            on=False,
        )
        == 0
    )

    with pytest.raises(PersonalScopeNotAllowed):
        await set_capability_personal_scope(
            rebac=cast(Any, rebac),
            agent_instance_store=cast(Any, None),
            catalog_entry=_app_entry(),
            scope="default",
        )


def _parked_deps(rebac: object) -> Any:
    return cast(
        Any,
        SimpleNamespace(
            configuration=_feature_configuration(
                enable_applications=True,
                application_sources=[_source("example", enabled=False)],
            ),
            team_dependencies=SimpleNamespace(rebac=rebac),
            get_kpi_writer=lambda: None,
        ),
    )


def _app_grant(team_id: str, relation: RelationType) -> Relation:
    return Relation(
        subject=RebacReference(Resource.TEAM, team_id),
        relation=relation,
        resource=RebacReference(Resource.CAPABILITY, "app__example"),
    )


@pytest.mark.asyncio
async def test_parked_application_grant_stays_revocable() -> None:
    """Parking withdraws an application from the catalog but keeps its gateway
    routes and its grants alive. Blocking the revoke as well would strand every
    grant, and un-parking would restore access with no admin action."""

    rebac = _TupleRebac()
    rebac.relations.add(_app_grant("team-a", RelationType.ENABLED))

    result = await capability_service.disable_team_capability(
        user=_user(),
        capability_id="app__example",
        team_id=TeamId("team-a"),
        deps=_parked_deps(rebac),
    )

    assert result.enabled is False
    assert _app_grant("team-a", RelationType.ENABLED) not in rebac.relations
    assert _app_grant("team-a", RelationType.DISABLED) in rebac.relations


@pytest.mark.asyncio
async def test_parked_application_grant_stays_resettable() -> None:
    rebac = _TupleRebac()
    rebac.relations.add(_app_grant("team-a", RelationType.ENABLED))

    await capability_service.reset_team_capability(
        user=_user(),
        capability_id="app__example",
        team_id=TeamId("team-a"),
        deps=_parked_deps(rebac),
    )

    assert not any(
        relation.subject.type is Resource.TEAM for relation in rebac.relations
    )


@pytest.mark.asyncio
async def test_parked_application_cannot_be_granted() -> None:
    """The revoke direction opens for a parked app; the grant direction does not."""

    rebac = _TupleRebac()

    with pytest.raises(CapabilityNotFound):
        await capability_service.enable_team_capability(
            user=_user(),
            capability_id="app__example",
            team_id=TeamId("team-a"),
            settings={},
            deps=_parked_deps(rebac),
        )

    assert not any(
        relation.relation is RelationType.ENABLED for relation in rebac.relations
    )
