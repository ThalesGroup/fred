"""Integration tests for RebacEngine implementations."""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Awaitable, Callable, cast

import grpc
import pytest
import pytest_asyncio
from pydantic import AnyUrl, ValidationError

from fred_core import (
    DocumentPermission,
    OpenFgaRebacConfig,
    OpenFgaRebacEngine,
    RebacDisabledResult,
    RebacEngine,
    RebacReference,
    Relation,
    RelationType,
    Resource,
    SpiceDbRebacConfig,
    SpiceDbRebacEngine,
    TagPermission,
)
from fred_core.security.structure import M2MSecurity

SPICEDB_ENDPOINT = os.getenv("SPICEDB_TEST_ENDPOINT", "localhost:50051")

MAX_STARTUP_ATTEMPTS = 40
STARTUP_BACKOFF_SECONDS = 0.5


def _integration_token() -> str:
    return f"itest-{uuid.uuid4().hex}"


def _unique_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _make_reference(resource: Resource, *, prefix: str | None = None) -> RebacReference:
    identifier = prefix or resource.value
    return RebacReference(type=resource, id=_unique_id(identifier))


async def _load_spicedb_engine() -> SpiceDbRebacEngine:
    """Create a SpiceDB-backed engine, skipping if the server is unavailable."""

    token = _integration_token()
    print("Using SpiceDB token:", token)
    probe_subject = RebacReference(type=Resource.USER, id=_unique_id("probe-user"))
    last_error: grpc.RpcError | None = None

    os.environ["M2M_CLIENT_SECRET"] = "test-secret"

    for attempt in range(1, MAX_STARTUP_ATTEMPTS + 1):
        try:
            engine = SpiceDbRebacEngine(
                SpiceDbRebacConfig(
                    endpoint=SPICEDB_ENDPOINT,
                    insecure=True,
                    sync_schema_on_init=True,
                ),
                M2MSecurity(
                    enabled=True,
                    realm_url=cast(AnyUrl, "http://app-keycloak:8080/realms/app"),
                    client_id="test-client",
                ),
                token=token,
            )
            # Trigger a cheap RPC call to confirm the server is reachable.
            await engine.lookup_resources(
                subject=probe_subject,
                permission=DocumentPermission.READ,
                resource_type=Resource.TAGS,
            )
            return engine
        except grpc.RpcError as exc:
            last_error = exc
            await asyncio.sleep(STARTUP_BACKOFF_SECONDS)
        except Exception as exc:
            pytest.skip(f"Failed to create SpiceDB engine: {exc}")

    pytest.skip(f"SpiceDB test server not available after retries: {last_error}")


async def _load_openfga_engine() -> RebacEngine:
    """Create an OpenFGA-backed engine, skipping if the server is unavailable."""

    api_url = os.getenv("OPENFGA_TEST_API_URL", "http://localhost:7080")

    if not api_url:
        pytest.skip(
            "OpenFGA test configuration missing. "
            "Set OPENFGA_TEST_API_URL and OPENFGA_TEST_STORE_ID."
        )

    store = _integration_token()
    print("Using OpenFGA store:", store)

    try:
        config = OpenFgaRebacConfig(
            api_url=api_url,  # pyright: ignore[reportArgumentType]
            store_name=store,
            sync_schema_on_init=True,
        )
        mock_m2m = M2MSecurity(
            enabled=True,
            realm_url=cast(AnyUrl, "http://app-keycloak:8080/realms/app"),
            client_id="test-client",
        )
    except ValidationError as exc:
        pytest.skip(f"Invalid OpenFGA configuration: {exc}")

    os.environ[mock_m2m.secret_env_var] = "test-secret"
    os.environ[config.token_env_var] = "test-token"

    try:
        engine = OpenFgaRebacEngine(config, mock_m2m, token=store)
    except Exception as exc:
        pytest.skip(f"Failed to create OpenFGA engine: {exc}")

    return engine


EngineScenario = tuple[str, Callable[[], Awaitable[RebacEngine]], str | None]

ENGINE_SCENARIOS: tuple[EngineScenario, ...] = (
    ("spicedb", _load_spicedb_engine, None),
    ("openfga", _load_openfga_engine, None),
)


@pytest_asyncio.fixture(params=ENGINE_SCENARIOS, ids=lambda scenario: scenario[0])
async def rebac_engine(request: pytest.FixtureRequest) -> RebacEngine:
    """Yield a configured RebacEngine implementation for each backend."""

    backend_id, loader, xfail_reason = request.param
    if xfail_reason:
        request.node.add_marker(pytest.mark.xfail(reason=xfail_reason, strict=False))

    engine = await loader()
    setattr(engine, "_backend", backend_id)
    return engine


@pytest.mark.integration
@pytest.mark.asyncio
async def test_owner_has_full_access(rebac_engine: RebacEngine) -> None:
    owner = _make_reference(Resource.USER, prefix="owner")
    tag = _make_reference(Resource.TAGS)
    stranger = _make_reference(Resource.USER, prefix="stranger")

    token = await rebac_engine.add_relation(
        Relation(subject=owner, relation=RelationType.OWNER, resource=tag)
    )

    assert await rebac_engine.has_permission(
        owner,
        TagPermission.DELETE,
        tag,
        consistency_token=token,
    )
    assert not await rebac_engine.has_permission(
        stranger,
        TagPermission.READ,
        tag,
        consistency_token=token,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_deleting_relation_revokes_access(
    rebac_engine: RebacEngine,
) -> None:
    owner = _make_reference(Resource.USER, prefix="owner")
    tag = _make_reference(Resource.TAGS)

    consistency_token = await rebac_engine.add_relation(
        Relation(subject=owner, relation=RelationType.OWNER, resource=tag)
    )

    assert await rebac_engine.has_permission(
        owner,
        TagPermission.DELETE,
        tag,
        consistency_token=consistency_token,
    )

    deletion_token = await rebac_engine.delete_relation(
        Relation(subject=owner, relation=RelationType.OWNER, resource=tag)
    )

    assert not await rebac_engine.has_permission(
        owner,
        TagPermission.DELETE,
        tag,
        consistency_token=deletion_token,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_reference_relations_removes_incoming_and_outgoing_edges(
    rebac_engine: RebacEngine,
) -> None:
    owner = _make_reference(Resource.USER, prefix="owner")
    tag = _make_reference(Resource.TAGS, prefix="tag")
    document = _make_reference(Resource.DOCUMENTS, prefix="document")

    token = await rebac_engine.add_relations(
        [
            Relation(subject=owner, relation=RelationType.OWNER, resource=tag),
            Relation(subject=tag, relation=RelationType.PARENT, resource=document),
        ]
    )

    assert await rebac_engine.has_permission(
        owner,
        TagPermission.DELETE,
        tag,
        consistency_token=token,
    )
    assert await rebac_engine.has_permission(
        owner,
        DocumentPermission.READ,
        document,
        consistency_token=token,
    )

    deletion_token = await rebac_engine.delete_all_relations_of_reference(tag)
    assert deletion_token is not None

    assert not await rebac_engine.has_permission(
        owner,
        TagPermission.DELETE,
        tag,
        consistency_token=deletion_token,
    )
    assert not await rebac_engine.has_permission(
        owner,
        DocumentPermission.READ,
        document,
        consistency_token=deletion_token,
    )
    assert (
        await rebac_engine.lookup_resources(
            subject=owner,
            permission=DocumentPermission.READ,
            resource_type=Resource.DOCUMENTS,
            consistency_token=deletion_token,
        )
        == []
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_group_members_inherit_permissions(
    rebac_engine: RebacEngine,
) -> None:
    alice = _make_reference(Resource.USER, prefix="alice")
    team = _make_reference(Resource.GROUP, prefix="team")
    tag = _make_reference(Resource.TAGS)

    token = await rebac_engine.add_relations(
        [
            Relation(subject=alice, relation=RelationType.MEMBER, resource=team),
            Relation(subject=team, relation=RelationType.EDITOR, resource=tag),
        ]
    )

    assert await rebac_engine.has_permission(
        alice,
        TagPermission.UPDATE,
        tag,
        consistency_token=token,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_parent_relationships_extend_permissions(
    rebac_engine: RebacEngine,
) -> None:
    owner = _make_reference(Resource.USER, prefix="owner")
    tag = _make_reference(Resource.TAGS, prefix="tag")
    document = _make_reference(Resource.DOCUMENTS, prefix="document")

    token = await rebac_engine.add_relations(
        [
            Relation(subject=owner, relation=RelationType.OWNER, resource=tag),
            Relation(subject=tag, relation=RelationType.PARENT, resource=document),
        ]
    )

    assert await rebac_engine.has_permission(
        owner,
        DocumentPermission.READ,
        document,
        consistency_token=token,
    )
    assert await rebac_engine.has_permission(
        owner,
        DocumentPermission.DELETE,
        document,
        consistency_token=token,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_lookup_subjects_returns_users_by_relation(
    rebac_engine: RebacEngine,
) -> None:
    tag = _make_reference(Resource.TAGS)
    owner = _make_reference(Resource.USER, prefix="owner")
    editor = _make_reference(Resource.USER, prefix="editor")
    viewer = _make_reference(Resource.USER, prefix="viewer")
    stranger = _make_reference(Resource.USER, prefix="stranger")
    stranger_tag = _make_reference(Resource.TAGS, prefix="stranger-tag")

    token = await rebac_engine.add_relations(
        [
            Relation(subject=owner, relation=RelationType.OWNER, resource=tag),
            Relation(subject=editor, relation=RelationType.EDITOR, resource=tag),
            Relation(subject=viewer, relation=RelationType.VIEWER, resource=tag),
            Relation(
                subject=stranger, relation=RelationType.VIEWER, resource=stranger_tag
            ),
        ]
    )

    owners = await rebac_engine.lookup_subjects(
        tag, RelationType.OWNER, Resource.USER, consistency_token=token
    )
    editors = await rebac_engine.lookup_subjects(
        tag, RelationType.EDITOR, Resource.USER, consistency_token=token
    )
    viewers = await rebac_engine.lookup_subjects(
        tag, RelationType.VIEWER, Resource.USER, consistency_token=token
    )

    assert not isinstance(owners, RebacDisabledResult)
    assert not isinstance(editors, RebacDisabledResult)
    assert not isinstance(viewers, RebacDisabledResult)

    assert {ref.id for ref in owners} == {owner.id}
    assert {ref.id for ref in editors} == {editor.id}
    assert {ref.id for ref in viewers} == {viewer.id}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_lookup_subjects_returns_groups_by_relation(
    rebac_engine: RebacEngine,
) -> None:
    tag = _make_reference(Resource.TAGS)
    owner_group = _make_reference(Resource.GROUP, prefix="owner-group")
    editor_group = _make_reference(Resource.GROUP, prefix="editor-group")
    viewer_group = _make_reference(Resource.GROUP, prefix="viewer-group")
    stray_group = _make_reference(Resource.GROUP, prefix="stray-group")
    stray_tag = _make_reference(Resource.TAGS, prefix="stray-tag")

    token = await rebac_engine.add_relations(
        [
            Relation(subject=owner_group, relation=RelationType.OWNER, resource=tag),
            Relation(subject=editor_group, relation=RelationType.EDITOR, resource=tag),
            Relation(subject=viewer_group, relation=RelationType.VIEWER, resource=tag),
            Relation(
                subject=stray_group,
                relation=RelationType.VIEWER,
                resource=stray_tag,
            ),
        ]
    )

    owner_groups = await rebac_engine.lookup_subjects(
        tag, RelationType.OWNER, Resource.GROUP, consistency_token=token
    )
    editor_groups = await rebac_engine.lookup_subjects(
        tag, RelationType.EDITOR, Resource.GROUP, consistency_token=token
    )
    viewer_groups = await rebac_engine.lookup_subjects(
        tag, RelationType.VIEWER, Resource.GROUP, consistency_token=token
    )

    assert not isinstance(owner_groups, RebacDisabledResult)
    assert not isinstance(editor_groups, RebacDisabledResult)
    assert not isinstance(viewer_groups, RebacDisabledResult)

    assert {ref.id for ref in owner_groups} == {owner_group.id}
    assert {ref.id for ref in editor_groups} == {editor_group.id}
    assert {ref.id for ref in viewer_groups} == {viewer_group.id}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_relations_filters_by_subject_type(
    rebac_engine: RebacEngine,
) -> None:
    if not rebac_engine.need_keycloak_sync:
        pytest.skip(
            "Keycloak sync not needed for this backend, list_relations not needed and not implemented"
        )

    team = _make_reference(Resource.GROUP, prefix="team")
    child_team = _make_reference(Resource.GROUP, prefix="team")
    member = _make_reference(Resource.USER, prefix="member")

    token = await rebac_engine.add_relations(
        [
            Relation(subject=member, relation=RelationType.MEMBER, resource=team),
            Relation(subject=team, relation=RelationType.MEMBER, resource=child_team),
        ]
    )

    user_memberships = await rebac_engine.list_relations(
        resource_type=Resource.GROUP,
        relation=RelationType.MEMBER,
        subject_type=Resource.USER,
        consistency_token=token,
    )
    group_memberships = await rebac_engine.list_relations(
        resource_type=Resource.GROUP,
        relation=RelationType.MEMBER,
        subject_type=Resource.GROUP,
        consistency_token=token,
    )

    assert not isinstance(user_memberships, RebacDisabledResult)
    assert not isinstance(group_memberships, RebacDisabledResult)

    assert {
        (relation.subject.type, relation.subject.id, relation.resource.id)
        for relation in user_memberships
    } == {(Resource.USER, member.id, team.id)}
    assert {
        (relation.subject.type, relation.subject.id, relation.resource.id)
        for relation in group_memberships
    } == {(Resource.GROUP, team.id, child_team.id)}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_documents_user_can_read(
    rebac_engine: RebacEngine,
) -> None:
    user = _make_reference(Resource.USER, prefix="reader")
    team = _make_reference(Resource.GROUP, prefix="team")
    tag = _make_reference(Resource.TAGS, prefix="tag")
    sub_tag = _make_reference(Resource.TAGS, prefix="subtag")
    document1 = _make_reference(Resource.DOCUMENTS, prefix="doc1")
    document2 = _make_reference(Resource.DOCUMENTS, prefix="doc2")

    private_tag = _make_reference(Resource.TAGS, prefix="private-tag")
    private_document = _make_reference(Resource.DOCUMENTS, prefix="doc-private")

    token = await rebac_engine.add_relations(
        [
            Relation(subject=user, relation=RelationType.MEMBER, resource=team),
            Relation(subject=team, relation=RelationType.EDITOR, resource=tag),
            # Add document1 directly in tag
            Relation(subject=tag, relation=RelationType.PARENT, resource=document1),
            # Add document2 via a sub-tag
            Relation(subject=tag, relation=RelationType.PARENT, resource=sub_tag),
            Relation(subject=sub_tag, relation=RelationType.PARENT, resource=document2),
            # Private document in private tag not accessible to the user
            Relation(
                subject=private_tag,
                relation=RelationType.PARENT,
                resource=private_document,
            ),
        ]
    )

    readable_documents = await rebac_engine.lookup_resources(
        subject=user,
        permission=DocumentPermission.READ,
        resource_type=Resource.DOCUMENTS,
        consistency_token=token,
    )

    assert not isinstance(readable_documents, RebacDisabledResult)

    readable_document_ids = {reference.id for reference in readable_documents}
    assert readable_document_ids == {document1.id, document2.id}, (
        f"Unexpected documents for {user.id}: {readable_document_ids}"
    )

    assert all(
        reference.type is Resource.DOCUMENTS for reference in readable_documents
    ), "Lookup must return document references"

    assert await rebac_engine.has_permission(
        user,
        DocumentPermission.READ,
        document1,
        consistency_token=token,
    )

    assert not await rebac_engine.has_permission(
        user,
        DocumentPermission.READ,
        private_document,
        consistency_token=token,
    )
