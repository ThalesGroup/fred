# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0

"""Team enablement of configured Knowledge Base definitions.

The ReBAC engine is faked: these assert the relations written and the
permission they resolve to, mirroring the `knowledge_base_definition` type in
schema.fga. They never reach a live OpenFGA.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from control_plane_backend.capabilities.enablement import (
    grant_team_enablement,
    revoke_team_enablement,
)
from control_plane_backend.knowledge_bases.store import (
    KnowledgeBaseProviderConflict,
)
from fred_core import Resource
from fred_core.security.models import AuthorizationError
from fred_core.security.rebac.knowledge_base_authz import (
    knowledge_base_catalog_id,
    knowledge_base_definition_ref,
    knowledge_base_provider_and_definition,
)
from fred_core.security.rebac.rebac_engine import (
    KnowledgeBaseDefinitionPermission,
    RebacReference,
)
from fred_core.security.structure import SERVICE_AGENT_ROLE
from fred_sdk.knowledge_base import KnowledgeBaseDeclaration

# --------------------------------------------------------------------------
# Fake ReBAC — models the `knowledge_base_definition` type's computed can_use
# --------------------------------------------------------------------------


class _FakeRebac:
    def __init__(self, *, platform_admin: bool = True) -> None:
        self.relations: set[tuple[str, str, str]] = set()
        self.platform_admin = platform_admin
        self.invalidations = 0

    @staticmethod
    def _name(value: Any) -> str:
        return str(getattr(value, "value", value))

    @classmethod
    def _key(cls, relation: Any) -> tuple[str, str, str]:
        return (
            f"{cls._name(relation.subject.type)}:{relation.subject.id}",
            cls._name(relation.relation),
            f"{cls._name(relation.resource.type)}:{relation.resource.id}",
        )

    async def add_relation(self, relation: Any, actor_uid: str | None = None) -> None:
        del actor_uid
        self.relations.add(self._key(relation))

    async def delete_relation(self, relation: Any) -> None:
        self.relations.discard(self._key(relation))

    async def check_user_permission_or_raise(self, user: Any, permission, resource):
        del user, permission, resource
        if not self.platform_admin:
            raise AuthorizationError(
                "admin-1", "can_manage_platform", Resource.ORGANIZATION
            )

    # `can_use: (enabled or inherited) but not disabled`
    def can_use(self, *, team_id: str, definition_id: str) -> bool:
        target = f"{Resource.KNOWLEDGE_BASE_DEFINITION.value}:{definition_id}"
        team = f"{Resource.TEAM.value}:{team_id}"
        if (team, "disabled", target) in self.relations:
            return False
        return (team, "enabled", target) in self.relations

    async def lookup_resources(
        self, subject, permission, resource_type, **kwargs
    ) -> list[Any]:
        del permission, resource_type, kwargs
        team_id = str(subject.id)
        return [
            type("_Ref", (), {"id": definition_id})()
            for definition_id in self._definition_ids()
            if self.can_use(team_id=team_id, definition_id=definition_id)
        ]

    def _definition_ids(self) -> set[str]:
        prefix = f"{Resource.KNOWLEDGE_BASE_DEFINITION.value}:"
        return {
            resource[len(prefix) :]
            for _, _, resource in self.relations
            if resource.startswith(prefix)
        }

    def anchored(self, definition_id: str) -> bool:
        target = f"{Resource.KNOWLEDGE_BASE_DEFINITION.value}:{definition_id}"
        return any(
            rel == "organization" and res == target for _, rel, res in self.relations
        )


class _User:
    uid = "admin-1"


def _manifest_payload(definition_id: str = "http-markdown") -> dict[str, Any]:
    return {
        "id": definition_id,
        "version": "1.0.0",
        "name": "HTTP Markdown",
        "description": "Synchronize Markdown documents",
        "configuration_fields": [],
    }


def _declaration(definition_id: str = "http-markdown") -> KnowledgeBaseDeclaration:
    return KnowledgeBaseDeclaration.model_validate(_manifest_payload(definition_id))


# --------------------------------------------------------------------------
# The dedicated authorization resource
# --------------------------------------------------------------------------


# The authorization object id is the catalog id minus its `kb__` prefix, so two
# segments: a definition id alone does not identify an object.
DEFINITION_OBJECT_ID = "acme-kb__http-markdown"


def test_definition_reference_uses_its_own_resource_type() -> None:
    ref = knowledge_base_definition_ref(DEFINITION_OBJECT_ID)
    assert isinstance(ref, RebacReference)
    assert ref.type is Resource.KNOWLEDGE_BASE_DEFINITION
    assert ref.id == DEFINITION_OBJECT_ID


def test_definition_type_is_neither_capability_nor_app() -> None:
    kind = Resource.KNOWLEDGE_BASE_DEFINITION
    assert kind is not Resource.CAPABILITY
    assert kind is not Resource.APP
    assert kind.value == "knowledge_base_definition"


def test_permission_vocabulary_is_use_and_manage() -> None:
    assert {p.value for p in KnowledgeBaseDefinitionPermission} == {
        "can_use",
        "can_manage",
    }


# --------------------------------------------------------------------------
# enable / disable through the shared enablement operation
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_team_cannot_use_a_definition_before_enablement() -> None:
    rebac = _FakeRebac()
    assert not rebac.can_use(team_id="team-1", definition_id=DEFINITION_OBJECT_ID)


@pytest.mark.asyncio
async def test_enabling_grants_can_use_and_anchors_the_resource() -> None:
    rebac = _FakeRebac()
    await grant_team_enablement(
        rebac,  # type: ignore[arg-type]
        resource=knowledge_base_definition_ref(DEFINITION_OBJECT_ID),
        team_id="team-1",  # type: ignore[arg-type]
        updated_by="admin-1",
    )
    assert rebac.can_use(team_id="team-1", definition_id=DEFINITION_OBJECT_ID)
    assert rebac.anchored(DEFINITION_OBJECT_ID)


@pytest.mark.asyncio
async def test_disabling_writes_an_explicit_opt_out_and_removes_can_use() -> None:
    rebac = _FakeRebac()
    ref = knowledge_base_definition_ref(DEFINITION_OBJECT_ID)
    await grant_team_enablement(
        rebac,  # type: ignore[arg-type]
        resource=ref,
        team_id="team-1",  # type: ignore[arg-type]
        updated_by="admin-1",
    )
    await revoke_team_enablement(
        rebac,  # type: ignore[arg-type]
        resource=ref,
        team_id="team-1",  # type: ignore[arg-type]
        updated_by="admin-1",
        ensure_anchor=True,
    )
    assert not rebac.can_use(team_id="team-1", definition_id=DEFINITION_OBJECT_ID)
    key = (
        "team:team-1",
        "disabled",
        f"knowledge_base_definition:{DEFINITION_OBJECT_ID}",
    )
    assert key in rebac.relations


@pytest.mark.asyncio
async def test_re_enabling_clears_the_opt_out() -> None:
    rebac = _FakeRebac()
    ref = knowledge_base_definition_ref(DEFINITION_OBJECT_ID)
    for _ in range(2):
        await revoke_team_enablement(
            rebac,  # type: ignore[arg-type]
            resource=ref,
            team_id="team-1",  # type: ignore[arg-type]
            updated_by="admin-1",
            ensure_anchor=True,
        )
        await grant_team_enablement(
            rebac,  # type: ignore[arg-type]
            resource=ref,
            team_id="team-1",  # type: ignore[arg-type]
            updated_by="admin-1",
        )
    assert rebac.can_use(team_id="team-1", definition_id=DEFINITION_OBJECT_ID)


@pytest.mark.asyncio
async def test_enablement_is_scoped_to_one_team_and_one_definition() -> None:
    rebac = _FakeRebac()
    await grant_team_enablement(
        rebac,  # type: ignore[arg-type]
        resource=knowledge_base_definition_ref(DEFINITION_OBJECT_ID),
        team_id="team-1",  # type: ignore[arg-type]
        updated_by="admin-1",
    )
    assert not rebac.can_use(team_id="team-2", definition_id=DEFINITION_OBJECT_ID)
    assert not rebac.can_use(team_id="team-1", definition_id="wiki")


# --------------------------------------------------------------------------
# service-level behaviour
# --------------------------------------------------------------------------


PROVIDER = "acme-kb"
PROVIDER_CLIENT = "kb-acme"


class _FakeStore:
    """In-memory stand-in, enforcing the same provider binding as the real one."""

    def __init__(self, declarations: list[KnowledgeBaseDeclaration]) -> None:
        self.rows: dict[tuple[str, str], Any] = {}
        for declaration in declarations:
            self.rows[(PROVIDER, declaration.id)] = _published(
                PROVIDER, declaration, PROVIDER_CLIENT
            )

    async def get(self, provider_id: str, definition_id: str) -> Any:
        return self.rows.get((provider_id, definition_id))

    async def list_all(self) -> list[Any]:
        return [self.rows[key] for key in sorted(self.rows)]

    async def upsert(
        self,
        *,
        provider_id: str,
        declaration: KnowledgeBaseDeclaration,
        client_id: str,
    ) -> Any:
        owner = next(
            (row.client_id for key, row in self.rows.items() if key[0] == provider_id),
            None,
        )
        if owner is not None and owner != client_id:
            raise KnowledgeBaseProviderConflict(
                f"Provider {provider_id!r} is bound to another client"
            )
        self.rows[(provider_id, declaration.id)] = _published(
            provider_id, declaration, client_id
        )
        return self.rows[(provider_id, declaration.id)]


def _published(
    provider_id: str, declaration: KnowledgeBaseDeclaration, client_id: str
) -> Any:
    return type(
        "_Published",
        (),
        {
            "provider_id": provider_id,
            "definition_id": declaration.id,
            "client_id": client_id,
            "version": declaration.version,
            "name": declaration.name,
            "description": declaration.description,
            "configuration_fields": list(declaration.configuration_fields),
        },
    )()


class _FakeDeps:
    def __init__(
        self, rebac: _FakeRebac, declarations: list[KnowledgeBaseDeclaration]
    ) -> None:
        self.team_dependencies = type("_TD", (), {"rebac": rebac})()
        self.store = _FakeStore(declarations)

    def get_knowledge_base_definition_store(self) -> _FakeStore:
        return self.store


class _CatalogDeps:
    """Deps for `aggregate_capability_catalog`: no pod, no application."""

    def __init__(self, declarations: list[KnowledgeBaseDeclaration]) -> None:
        self.configuration = SimpleNamespace(
            platform=SimpleNamespace(
                frontend=SimpleNamespace(
                    feature_flags=SimpleNamespace(enableApplications=False)
                ),
                application_sources=[],
                runtime_catalog_sources=[],
            )
        )
        self.store = _FakeStore(declarations)

    def get_knowledge_base_definition_store(self) -> _FakeStore:
        return self.store


@pytest.mark.asyncio
async def test_published_definitions_are_projected_into_the_admin_catalog() -> None:
    """A definition reaches Platform Admin as one more catalog row.

    Same surface as every other kind, so there is no second admin page and no
    second enablement service — only the ReBAC type underneath differs.
    """

    from control_plane_backend.capabilities.catalog import (
        aggregate_capability_catalog,
    )

    catalog = await aggregate_capability_catalog(
        cast(Any, _CatalogDeps([_declaration()]))
    )

    entry = catalog[knowledge_base_catalog_id("acme-kb", "http-markdown")]
    assert entry.kind == "knowledge_base"
    # Existence is not availability: nothing here reports on a pod.
    assert not {"online", "healthy", "connected", "status"} & set(entry.model_dump())


@pytest.mark.asyncio
async def test_the_projection_never_collides_with_a_pod_advertised_id() -> None:
    """The `kb__` prefix is what keeps one flat catalog unambiguous."""

    from control_plane_backend.capabilities.catalog import (
        aggregate_capability_catalog,
    )

    catalog = await aggregate_capability_catalog(
        cast(Any, _CatalogDeps([_declaration()]))
    )

    assert "http-markdown" not in catalog
    catalog_id = knowledge_base_catalog_id("acme-kb", "http-markdown")
    assert catalog_id == "kb__acme-kb__http-markdown"
    # The provider is a segment of its own, so two providers may each expose a
    # definition of the same name without colliding.
    assert catalog_id != knowledge_base_catalog_id("globex-kb", "http-markdown")
    assert knowledge_base_provider_and_definition(catalog_id) == (
        "acme-kb",
        "http-markdown",
    )


def test_the_catalog_admits_knowledge_bases_as_their_own_kind() -> None:
    from fred_sdk.contracts.capability.manifest import CapabilityCatalogEntry

    kinds = str(CapabilityCatalogEntry.model_fields["kind"].annotation)
    assert "knowledge_base" in kinds
    # The catalog carries the kind; it never carries the ReBAC type name.
    assert "knowledge_base_definition" not in kinds


def test_enablement_routes_a_definition_to_its_own_rebac_type() -> None:
    """Sharing the catalog must not share the authorization object.

    This is the property the separate admin surface used to carry: a grant on
    a Knowledge Base row writes `knowledge_base_definition`, never `capability`
    or `app`, so no capability or application grant can make one usable.
    """

    from control_plane_backend.capabilities.enablement import enablement_ref
    from fred_sdk.contracts.capability.manifest import (
        CapabilityCatalogEntry,
        TeamScopePolicy,
    )

    entry = CapabilityCatalogEntry(
        id=knowledge_base_catalog_id("acme-kb", "http-markdown"),
        version="1.0.0",
        name="HTTP Markdown",
        description="HTTP Markdown",
        icon="database",
        kind="knowledge_base",
        team_scope=TeamScopePolicy.ADMIN_GATED,
    )

    ref = enablement_ref(entry)
    assert ref == knowledge_base_definition_ref(DEFINITION_OBJECT_ID)
    assert ref.type is Resource.KNOWLEDGE_BASE_DEFINITION
    assert ref.type is not Resource.CAPABILITY
    assert ref.type is not Resource.APP


# --------------------------------------------------------------------------
# Publication: one write at deployment, bound to the publishing client
# --------------------------------------------------------------------------


class _Client:
    """A confidential M2M identity, as `get_current_user` resolves one."""

    uid = "service-account-kb"

    def __init__(self, client_id: str | None, *, service: bool = True) -> None:
        self.client_id = client_id
        self.roles = [SERVICE_AGENT_ROLE] if service else ["admin"]


@pytest.mark.asyncio
async def test_first_publication_creates_the_definition_and_binds_its_client() -> None:
    from control_plane_backend.knowledge_bases import service

    deps = _FakeDeps(_FakeRebac(), [])
    result = await service.publish_definition(
        user=_Client(PROVIDER_CLIENT),  # type: ignore[arg-type]
        provider_id=PROVIDER,
        declaration=_declaration(),
        deps=deps,  # type: ignore[arg-type]
    )
    assert (result.provider_id, result.definition_id) == (PROVIDER, "http-markdown")
    stored = await deps.store.get(PROVIDER, "http-markdown")
    assert stored is not None
    assert stored.client_id == PROVIDER_CLIENT


@pytest.mark.asyncio
async def test_the_same_client_may_republish() -> None:
    from control_plane_backend.knowledge_bases import service

    deps = _FakeDeps(_FakeRebac(), [])
    for _ in range(2):
        await service.publish_definition(
            user=_Client(PROVIDER_CLIENT),  # type: ignore[arg-type]
            provider_id=PROVIDER,
            declaration=_declaration(),
            deps=deps,  # type: ignore[arg-type]
        )
    assert len(deps.store.rows) == 1


@pytest.mark.asyncio
async def test_another_client_cannot_take_over_a_definition() -> None:
    from control_plane_backend.knowledge_bases import service

    deps = _FakeDeps(_FakeRebac(), [_declaration()])
    with pytest.raises(KnowledgeBaseProviderConflict):
        await service.publish_definition(
            user=_Client("kb-somebody-else"),  # type: ignore[arg-type]
            provider_id=PROVIDER,
            declaration=_declaration(),
            deps=deps,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_publishing_without_a_client_identity_is_refused() -> None:
    from control_plane_backend.knowledge_bases import service

    deps = _FakeDeps(_FakeRebac(), [])
    with pytest.raises(service.KnowledgeBaseClientMismatch):
        await service.publish_definition(
            user=_Client(None),  # type: ignore[arg-type]
            provider_id=PROVIDER,
            declaration=_declaration(),
            deps=deps,  # type: ignore[arg-type]
        )
    assert deps.store.rows == {}


@pytest.mark.asyncio
async def test_a_user_session_cannot_publish() -> None:
    from control_plane_backend.knowledge_bases import service

    deps = _FakeDeps(_FakeRebac(), [])
    # An ordinary signed-in user's token carries the frontend's `azp`; without
    # the service-identity gate that alone would be enough to publish.
    with pytest.raises(service.KnowledgeBaseClientMismatch):
        await service.publish_definition(
            user=_Client("app", service=False),  # type: ignore[arg-type]
            provider_id=PROVIDER,
            declaration=_declaration(),
            deps=deps,  # type: ignore[arg-type]
        )
    assert deps.store.rows == {}


@pytest.mark.asyncio
async def test_the_admin_surface_carries_no_declared_fields() -> None:
    """The admin catalog never collects a configuration value, so it shows none.

    A `FieldSpec` routinely names internal endpoints in its title or
    placeholder; it belongs to an enabled team's instance form, not to a
    platform-wide catalog row.
    """

    from control_plane_backend.capabilities.catalog import (
        aggregate_capability_catalog,
    )

    catalog = await aggregate_capability_catalog(
        cast(Any, _CatalogDeps([_declaration()]))
    )

    presented = catalog[
        knowledge_base_catalog_id("acme-kb", "http-markdown")
    ].model_dump()
    assert "configuration_fields" not in presented
    assert not {"fields", "field_count"} & set(presented)


# --------------------------------------------------------------------------
# One predicate, not a dozen kind checks: a Knowledge Base takes the same
# path as an application everywhere an agent capability's machinery does not
# apply. These pin the properties the per-kind branches used to get wrong.
# --------------------------------------------------------------------------


def test_a_definition_takes_the_projected_product_object_path() -> None:
    from control_plane_backend.capabilities.enablement import (
        is_projected_product_object,
    )
    from fred_sdk.contracts.capability.manifest import (
        CapabilityCatalogEntry,
        TeamScopePolicy,
    )

    def entry(kind: str, entry_id: str) -> CapabilityCatalogEntry:
        return CapabilityCatalogEntry(
            id=entry_id,
            version="1",
            name=entry_id,
            description=entry_id,
            icon="database",
            kind=kind,  # type: ignore[arg-type]
            team_scope=TeamScopePolicy.ADMIN_GATED,
        )

    assert is_projected_product_object(entry("knowledge_base", "kb__x"))
    assert is_projected_product_object(entry("app", "app__x"))
    # An agent capability keeps its instance lifecycle, settings and personal class.
    for kind in ("tool", "agent", "model"):
        assert not is_projected_product_object(entry(kind, "x"))


def test_a_definition_has_no_personal_space_scope() -> None:
    """Its ReBAC type carries no personal class, so the write is refused.

    Accepting it would write `personal_on` onto an object that has no such
    relation and report success for a grant nobody ever receives.
    """

    from control_plane_backend.capabilities.enablement import (
        PersonalScopeNotAllowed,
        _reject_personal_team_projected_grant,
    )
    from fred_sdk.contracts.capability.manifest import (
        CapabilityCatalogEntry,
        TeamScopePolicy,
    )

    entry = CapabilityCatalogEntry(
        id=knowledge_base_catalog_id("acme-kb", "http-markdown"),
        version="1.0.0",
        name="HTTP Markdown",
        description="HTTP Markdown",
        icon="database",
        kind="knowledge_base",
        team_scope=TeamScopePolicy.ADMIN_GATED,
    )

    with pytest.raises(Exception) as raised:
        _reject_personal_team_projected_grant(entry, "personal")  # type: ignore[arg-type]
    assert "personal" in str(raised.value)
    assert PersonalScopeNotAllowed  # imported for the sibling refusal path


@pytest.mark.asyncio
async def test_managing_an_unpublished_definition_anchors_nothing() -> None:
    """The gate must refuse before touching an arbitrary path parameter.

    Anchoring first would let any authenticated caller grow tuples on the
    `capability` type — which is not this id's authorization object anyway.
    """

    from control_plane_backend.capabilities.service import (
        CapabilityNotFound,
        _require_can_manage,
    )

    rebac = _FakeRebac()
    deps = _CatalogDeps([])  # nothing published

    with pytest.raises(CapabilityNotFound):
        await _require_can_manage(
            rebac,  # type: ignore[arg-type]
            _User(),  # type: ignore[arg-type]
            knowledge_base_catalog_id("acme-kb", "never-published"),
            deps=cast(Any, deps),
        )
    assert rebac.relations == set()


@pytest.mark.asyncio
async def test_a_provider_namespace_belongs_to_one_client() -> None:
    """The binding is per PROVIDER, not per definition.

    A provider exposes several Knowledge Bases; claiming the namespace once is
    what stops a second workload writing anywhere inside it — including under a
    definition id nobody has published yet.
    """

    from control_plane_backend.knowledge_bases import service

    deps = _FakeDeps(_FakeRebac(), [])
    await service.publish_definition(
        user=_Client(PROVIDER_CLIENT),  # type: ignore[arg-type]
        provider_id=PROVIDER,
        declaration=_declaration(),
        deps=deps,  # type: ignore[arg-type]
    )

    # Same provider, a definition id that does not exist yet: still refused.
    with pytest.raises(KnowledgeBaseProviderConflict):
        await service.publish_definition(
            user=_Client("kb-somebody-else"),  # type: ignore[arg-type]
            provider_id=PROVIDER,
            declaration=_declaration(definition_id="sharepoint"),
            deps=deps,  # type: ignore[arg-type]
        )
    assert len(deps.store.rows) == 1


@pytest.mark.asyncio
async def test_two_providers_may_expose_the_same_definition_name() -> None:
    """Namespacing by provider is what makes this possible at all."""

    from control_plane_backend.knowledge_bases import service

    deps = _FakeDeps(_FakeRebac(), [])
    for provider, client in ((PROVIDER, PROVIDER_CLIENT), ("globex-kb", "kb-globex")):
        await service.publish_definition(
            user=_Client(client),  # type: ignore[arg-type]
            provider_id=provider,
            declaration=_declaration(),
            deps=deps,  # type: ignore[arg-type]
        )

    assert set(deps.store.rows) == {
        (PROVIDER, "http-markdown"),
        ("globex-kb", "http-markdown"),
    }


def test_publication_does_not_gate_a_machine_on_human_gcu_admission() -> None:
    """The publisher is a confidential client, not a person.

    `get_current_user` enforces persisted GCU acceptance, which needs a user row
    and somebody to accept terms. A Knowledge Base pod has neither, so gating
    publication on it makes the route unreachable wherever `app.gcu_version` is
    configured — as the repository's own default control-plane profile does.
    Asserted on the route, because the service-level tests below sit under the
    dependency and cannot see it.
    """
    from collections.abc import Iterator

    from control_plane_backend.knowledge_bases.api import router
    from fastapi.dependencies.models import Dependant
    from fastapi.routing import APIRoute
    from fred_core import get_current_user, get_current_user_without_gcu

    route = next(
        candidate
        for candidate in router.routes
        if isinstance(candidate, APIRoute) and "providers" in candidate.path
    )

    def dependency_calls(dependant: Dependant) -> Iterator[object]:
        yield dependant.call
        for sub in dependant.dependencies:
            yield from dependency_calls(sub)

    resolved = set(dependency_calls(route.dependant))

    assert get_current_user_without_gcu in resolved
    assert get_current_user not in resolved
