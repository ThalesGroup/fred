"""Integration tests for the SpiceDbRebacEngine."""

from __future__ import annotations

import time
import uuid

import grpc
import pytest

from fred_core.security.models import Action, Resource
from fred_core.security.rebac.rebac_engine import RebacReference, Relation, RelationType
from fred_core.security.rebac.spicedb_engine import SpiceDbRebacEngine

SPICEDB_ENDPOINT = "localhost:50051"


def _integration_token() -> str:
    return f"itest-{uuid.uuid4().hex}"


def _unique_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _make_reference(resource: Resource, *, prefix: str | None = None) -> RebacReference:
    identifier = prefix or resource.value
    return RebacReference(type=resource, id=_unique_id(identifier))


MAX_STARTUP_ATTEMPTS = 40
STARTUP_BACKOFF_SECONDS = 0.5


@pytest.fixture()
def spicedb_engine() -> SpiceDbRebacEngine:
    """Provide a SpiceDB-backed engine, skipping if the server is unavailable."""

    token = _integration_token()
    print("Using SpiceDB token:", token)
    probe_subject = RebacReference(type=Resource.USER, id=_unique_id("probe-user"))
    last_error: grpc.RpcError | None = None

    for attempt in range(1, MAX_STARTUP_ATTEMPTS + 1):
        try:
            engine = SpiceDbRebacEngine(
                endpoint=SPICEDB_ENDPOINT,
                token=token,
                insecure=True,
            )
            # Trigger a cheap RPC call to confirm the server is reachable.
            engine.lookup_resources(
                subject=probe_subject,
                permission=Action.READ,
                resource_type=Resource.TAGS,
            )
            return engine
        except grpc.RpcError as exc:  # pragma: no cover - depends on external service
            last_error = exc
            time.sleep(STARTUP_BACKOFF_SECONDS)

    pytest.skip(
        "SpiceDB test server not available after retries: "
        f"{last_error}"  # pragma: no cover - depends on external service
    )


@pytest.mark.integration
def test_owner_has_full_access(spicedb_engine: SpiceDbRebacEngine) -> None:
    owner = _make_reference(Resource.USER, prefix="owner")
    tag = _make_reference(Resource.TAGS)
    stranger = _make_reference(Resource.USER, prefix="stranger")

    token = spicedb_engine.add_relation(
        Relation(subject=owner, relation=RelationType.OWNER, resource=tag)
    )

    assert spicedb_engine.has_permission(
        owner,
        Action.DELETE,
        tag,
        consistency_token=token,
    )
    assert not spicedb_engine.has_permission(
        stranger,
        Action.READ,
        tag,
        consistency_token=token,
    )


@pytest.mark.integration
def test_group_members_inherit_permissions(spicedb_engine: SpiceDbRebacEngine) -> None:
    alice = _make_reference(Resource.USER, prefix="alice")
    team = _make_reference(Resource.GROUP, prefix="team")
    tag = _make_reference(Resource.TAGS)

    token = spicedb_engine.add_relations(
        [
            Relation(subject=alice, relation=RelationType.MEMBER, resource=team),
            Relation(subject=team, relation=RelationType.EDITOR, resource=tag),
        ]
    )

    assert spicedb_engine.has_permission(
        alice,
        Action.UPDATE,
        tag,
        consistency_token=token,
    )


@pytest.mark.integration
def test_parent_relationships_extend_permissions(
    spicedb_engine: SpiceDbRebacEngine,
) -> None:
    owner = _make_reference(Resource.USER, prefix="owner")
    tag = _make_reference(Resource.TAGS, prefix="tag")
    document = _make_reference(Resource.DOCUMENTS, prefix="document")

    token = spicedb_engine.add_relations(
        [
            Relation(subject=owner, relation=RelationType.OWNER, resource=tag),
            Relation(subject=tag, relation=RelationType.PARENT, resource=document),
        ]
    )

    assert spicedb_engine.has_permission(
        owner,
        Action.READ,
        document,
        consistency_token=token,
    )
    assert spicedb_engine.has_permission(
        owner,
        Action.DELETE,
        document,
        consistency_token=token,
    )


@pytest.mark.integration
def test_list_documents_user_can_read(spicedb_engine: SpiceDbRebacEngine) -> None:
    user = _make_reference(Resource.USER, prefix="reader")
    team = _make_reference(Resource.GROUP, prefix="team")
    tag = _make_reference(Resource.TAGS, prefix="tag")
    subTag = _make_reference(Resource.TAGS, prefix="subtag")
    document1 = _make_reference(Resource.DOCUMENTS, prefix="doc1")
    document2 = _make_reference(Resource.DOCUMENTS, prefix="doc2")

    private_tag = _make_reference(Resource.TAGS, prefix="private-tag")
    private_document = _make_reference(Resource.DOCUMENTS, prefix="doc-private")

    token = spicedb_engine.add_relations(
        [
            Relation(subject=user, relation=RelationType.MEMBER, resource=team),
            Relation(subject=team, relation=RelationType.EDITOR, resource=tag),
            # Add document1 directly in tag
            Relation(subject=tag, relation=RelationType.PARENT, resource=document1),
            # Add document2 via a sub-tag
            Relation(subject=tag, relation=RelationType.PARENT, resource=subTag),
            Relation(subject=subTag, relation=RelationType.PARENT, resource=document2),
            # Private document in private tag not accessible to the user
            Relation(
                subject=private_tag,
                relation=RelationType.PARENT,
                resource=private_document,
            ),
        ]
    )

    readable_documents = spicedb_engine.lookup_resources(
        subject=user,
        permission=Action.READ,
        resource_type=Resource.DOCUMENTS,
        consistency_token=token,
    )
    readable_document_ids = {reference.id for reference in readable_documents}
    assert readable_document_ids == {document1.id, document2.id}, (
        f"Unexpected documents for {user.id}: {readable_document_ids}"
    )

    assert all(
        reference.type is Resource.DOCUMENTS for reference in readable_documents
    ), "Lookup must return document references"

    assert spicedb_engine.has_permission(
        user,
        Action.READ,
        document1,
        consistency_token=token,
    )

    assert not spicedb_engine.has_permission(
        user,
        Action.READ,
        private_document,
        consistency_token=token,
    )
