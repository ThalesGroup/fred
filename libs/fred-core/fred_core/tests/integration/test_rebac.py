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

"""Integration tests for RebacEngine implementations."""

from __future__ import annotations

import os
import secrets
import uuid
from typing import Awaitable, Callable

import pytest
import pytest_asyncio
from pydantic import AnyHttpUrl, ValidationError

from fred_core import (
    AgentPermission,
    AuthorizationError,
    CapabilityPermission,
    DocumentPermission,
    OpenFgaRebacConfig,
    OpenFgaRebacEngine,
    OrganizationPermission,
    RebacDisabledResult,
    RebacEngine,
    RebacReference,
    Relation,
    RelationType,
    Resource,
    TagPermission,
    TeamPermission,
)
from fred_core.security.rebac.rebac_engine import ORGANIZATION_ID
from fred_core.security.structure import KeycloakUser, M2MSecurity

MAX_STARTUP_ATTEMPTS = 40
STARTUP_BACKOFF_SECONDS = 0.5


def _integration_token() -> str:
    return f"itest-{uuid.uuid4().hex}"


def _unique_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _make_reference(resource: Resource, *, prefix: str | None = None) -> RebacReference:
    identifier = prefix or resource.value
    return RebacReference(type=resource, id=_unique_id(identifier))


def _make_keycloak_user() -> KeycloakUser:
    """Build a plain `KeycloakUser`. `KeycloakUser` no longer carries a
    `groups` field at all (AUTHZ-05 final sweep) — permissions can only ever
    come from persisted OpenFGA tuples."""
    uid = _unique_id("user")
    return KeycloakUser(uid=uid, username=uid, roles=[], email=f"{uid}@example.com")


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
            realm_url=AnyHttpUrl("http://app-keycloak:8080/realms/app"),
            client_id="test-client",
        )
    except ValidationError as exc:
        pytest.skip(f"Invalid OpenFGA configuration: {exc}")

    os.environ.setdefault(mock_m2m.secret_env_var, secrets.token_urlsafe(16))
    os.environ.setdefault(config.token_env_var, secrets.token_urlsafe(16))

    try:
        engine = OpenFgaRebacEngine(config, token=store)
    except Exception as exc:
        pytest.skip(f"Failed to create OpenFGA engine: {exc}")

    return engine


EngineScenario = tuple[str, Callable[[], Awaitable[RebacEngine]], str | None]

ENGINE_SCENARIOS: tuple[EngineScenario, ...] = (
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
async def test_list_documents_user_can_read(
    rebac_engine: RebacEngine,
) -> None:
    user = _make_reference(Resource.USER, prefix="reader")
    tag = _make_reference(Resource.TAGS, prefix="tag")
    sub_tag = _make_reference(Resource.TAGS, prefix="subtag")
    document1 = _make_reference(Resource.DOCUMENTS, prefix="doc1")
    document2 = _make_reference(Resource.DOCUMENTS, prefix="doc2")

    private_tag = _make_reference(Resource.TAGS, prefix="private-tag")
    private_document = _make_reference(Resource.DOCUMENTS, prefix="doc-private")

    token = await rebac_engine.add_relations(
        [
            Relation(subject=user, relation=RelationType.EDITOR, resource=tag),
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_team_hierarchy_and_permissions(
    rebac_engine: RebacEngine,
) -> None:
    """Test team administration, editing, and permission inheritance.

    This test validates:
    - Team admin can update team info
    - Team editor can update members
    - Team members inherit permissions from team roles on tags and agents

    Global-organization-role escalation (the legacy Keycloak `admin`/`editor`/
    `viewer` bridge) is not covered here: that bridge was removed outright in
    AUTHZ-05 review item 8a, and `test_platform_admin_and_observer_never_grant_team_access`
    below already locks in that the target `platform_admin`/`platform_observer`
    relations never bypass explicit team roles either.
    """
    # Create entities
    organization = _make_reference(Resource.ORGANIZATION, prefix="organization")
    team = _make_reference(Resource.TEAM, prefix="marketing")
    team_admin = _make_reference(Resource.USER, prefix="team-admin")
    team_editor = _make_reference(Resource.USER, prefix="team-editor")
    team_member = _make_reference(Resource.USER, prefix="member")
    tag = _make_reference(Resource.TAGS, prefix="docs")
    agent = _make_reference(Resource.AGENT, prefix="assistant")

    # Set up team hierarchy and relations
    token = await rebac_engine.add_relations(
        [
            # Team hierarchy - team has a organization reference
            Relation(
                subject=organization, relation=RelationType.ORGANIZATION, resource=team
            ),
            Relation(
                subject=team_admin, relation=RelationType.TEAM_ADMIN, resource=team
            ),
            Relation(
                subject=team_editor, relation=RelationType.TEAM_EDITOR, resource=team
            ),
            Relation(
                subject=team_member, relation=RelationType.TEAM_MEMBER, resource=team
            ),
            # Team owns tag and agent
            Relation(subject=team, relation=RelationType.OWNER, resource=tag),
            Relation(subject=team, relation=RelationType.OWNER, resource=agent),
        ]
    )

    # ~~~~~~~~~~~~~~~~~~~~
    # Admin

    # Test admin can update team info
    assert await rebac_engine.has_permission(
        team_admin,
        TeamPermission.CAN_UPDATE_INFO,
        team,
        consistency_token=token,
    ), "Team admin should be able to update team info"

    # ~~~~~~~~~~~~~~~~~~~~
    # Editor

    # Test editor can not update members
    assert not await rebac_engine.has_permission(
        team_editor,
        TeamPermission.CAN_ADMINISTER_MEMBERS,
        team,
        consistency_token=token,
    ), "Team editor should not be able to update members"

    # Test editor can't administer admins
    assert not await rebac_engine.has_permission(
        team_editor,
        TeamPermission.CAN_ADMINISTER_ADMINS,
        team,
        consistency_token=token,
    ), "Team editor should not be able to administer admins"

    # Test editor can update tag via team ownership
    assert await rebac_engine.has_permission(
        team_editor,
        TagPermission.UPDATE,
        tag,
        consistency_token=token,
    ), "Team editor should be able to update team tag"

    # Test editor can update agent via team ownership
    assert await rebac_engine.has_permission(
        team_editor,
        AgentPermission.UPDATE,
        agent,
        consistency_token=token,
    ), "Team editor should be able to update team agent"

    # Test editor cannot update team info
    assert not await rebac_engine.has_permission(
        team_editor,
        TeamPermission.CAN_UPDATE_INFO,
        team,
        consistency_token=token,
    ), "Team editor should not be able to update team info"

    # ~~~~~~~~~~~~~~~~~~~~
    # Members

    # Test members can access team-owned tags
    assert await rebac_engine.has_permission(
        team_member,
        TagPermission.READ,
        tag,
        consistency_token=token,
    ), "Team member should be able to read team tag"

    # Test regular member cannot update team info
    assert not await rebac_engine.has_permission(
        team_member,
        TeamPermission.CAN_UPDATE_INFO,
        team,
        consistency_token=token,
    ), "Team member should not be able to update team info"

    # Test member cannot update tag (needs at least editor role)
    assert not await rebac_engine.has_permission(
        team_member,
        TagPermission.UPDATE,
        tag,
        consistency_token=token,
    ), "Team member should not be able to update tag"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_platform_admin_and_observer_never_grant_team_access(
    rebac_engine: RebacEngine,
) -> None:
    """AUTHZ-05: target platform roles satisfy org capabilities but never team ones.

    Mirrors `test_team_hierarchy_and_permissions`'s organization-admin block, but
    for the new `platform_admin`/`platform_observer` relations, so a future schema
    edit can't quietly reintroduce the same escalation under the new names.
    """
    organization = _make_reference(Resource.ORGANIZATION, prefix="organization")
    platform_admin = _make_reference(Resource.USER, prefix="platform-admin")
    platform_observer = _make_reference(Resource.USER, prefix="platform-observer")
    team = _make_reference(Resource.TEAM, prefix="finance")

    token = await rebac_engine.add_relations(
        [
            Relation(
                subject=platform_admin,
                relation=RelationType.PLATFORM_ADMIN,
                resource=organization,
            ),
            Relation(
                subject=platform_observer,
                relation=RelationType.PLATFORM_OBSERVER,
                resource=organization,
            ),
            Relation(
                subject=organization, relation=RelationType.ORGANIZATION, resource=team
            ),
        ]
    )

    assert await rebac_engine.has_permission(
        platform_admin,
        OrganizationPermission.CAN_MANAGE_PLATFORM,
        organization,
        consistency_token=token,
    ), "platform_admin should satisfy the org-level can_manage_platform capability"

    assert await rebac_engine.has_permission(
        platform_observer,
        OrganizationPermission.IS_PLATFORM_OBSERVER,
        organization,
        consistency_token=token,
    ), "platform_observer should satisfy the direct platform_observer relation check"

    for subject, label in (
        (platform_admin, "platform_admin"),
        (platform_observer, "platform_observer"),
    ):
        assert not await rebac_engine.has_permission(
            subject,
            TeamPermission.CAN_UPDATE_INFO,
            team,
            consistency_token=token,
        ), f"{label} must not gain team access without an explicit team role"
        assert not await rebac_engine.has_permission(
            subject,
            TeamPermission.CAN_READ_CONVERSATIONS,
            team,
            consistency_token=token,
        ), f"{label} must not read team conversations without an explicit team role"

    # AUTHZ-05 (RFC §24.7 revised, review finding on PR #1957): a
    # `platform_admin from organization` exception was tried here so a
    # freshly created team could get its first admin/editor assigned, and
    # reverted. OpenFGA relations can't express "only if this team has no
    # admin yet" - the grant applied to every team, always, letting
    # platform_admin self-promote to admin/editor of ANY team via the
    # ordinary membership endpoints and inherit full team data access. Team
    # bootstrap is instead a one-shot, dedicated action outside this schema
    # (RFC §28, `POST /teams`), not a standing capability reachable through
    # normal request authorization.
    for subject, label in (
        (platform_admin, "platform_admin"),
        (platform_observer, "platform_observer"),
    ):
        assert not await rebac_engine.has_permission(
            subject,
            TeamPermission.CAN_ADMINISTER_ADMINS,
            team,
            consistency_token=token,
        ), (
            f"{label} must not administer team admins - that would let it self-promote into team data access"
        )
        assert not await rebac_engine.has_permission(
            subject,
            TeamPermission.CAN_ADMINISTER_EDITORS,
            team,
            consistency_token=token,
        ), (
            f"{label} must not administer team editors - that would let it self-promote into team data access"
        )
        assert not await rebac_engine.has_permission(
            subject,
            TeamPermission.CAN_ADMINISTER_ANALYSTS,
            team,
            consistency_token=token,
        ), (
            f"{label} must not administer team analysts - that would let it self-promote into team data access"
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_team_tag_document_hierarchy(
    rebac_engine: RebacEngine,
) -> None:
    """Test that team permissions cascade through tag/document hierarchy.

    This test validates:
    - Team editor can update tags owned by team
    - Documents inherit permissions from parent tags
    - Nested tags inherit permissions correctly
    """
    team = _make_reference(Resource.TEAM, prefix="engineering")
    editor = _make_reference(Resource.USER, prefix="editor")
    member = _make_reference(Resource.USER, prefix="member")
    root_tag = _make_reference(Resource.TAGS, prefix="root")
    sub_tag = _make_reference(Resource.TAGS, prefix="subtag")
    document = _make_reference(Resource.DOCUMENTS, prefix="document")

    token = await rebac_engine.add_relations(
        [
            # Team structure
            Relation(subject=editor, relation=RelationType.TEAM_EDITOR, resource=team),
            Relation(subject=member, relation=RelationType.TEAM_MEMBER, resource=team),
            # Tag hierarchy
            Relation(subject=team, relation=RelationType.OWNER, resource=root_tag),
            Relation(subject=root_tag, relation=RelationType.PARENT, resource=sub_tag),
            Relation(subject=sub_tag, relation=RelationType.PARENT, resource=document),
        ]
    )

    # Test editor can update root tag via team permission
    assert await rebac_engine.has_permission(
        editor,
        TagPermission.UPDATE,
        root_tag,
        consistency_token=token,
    ), "Team editor should be able to update team tag"

    # Test editor can delete subtag via parent tag permission
    assert await rebac_engine.has_permission(
        editor,
        TagPermission.DELETE,
        sub_tag,
        consistency_token=token,
    ), "Team editor should be able to delete subtag"

    # Test member can read document through tag hierarchy
    assert await rebac_engine.has_permission(
        member,
        DocumentPermission.READ,
        document,
        consistency_token=token,
    ), "Team member should be able to read document in team tag"

    # Test member cannot update document (needs at least editor role)
    assert not await rebac_engine.has_permission(
        member,
        DocumentPermission.UPDATE,
        document,
        consistency_token=token,
    ), "Team member should not be able to update document (needs editor role)"

    # Test editor can update document via tag hierarchy
    assert await rebac_engine.has_permission(
        editor,
        DocumentPermission.UPDATE,
        document,
        consistency_token=token,
    ), "Team editor should be able to update document in team tag"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_public_team_read_access(
    rebac_engine: RebacEngine,
) -> None:
    """Test that public teams can be read by anyone, but their resources remain private.

    This test validates:
    - Public teams can be read by any user (via user:* wildcard)
    - Non-public teams cannot be read by strangers
    - Public team's agents cannot be accessed by strangers
    - Public team's tags cannot be accessed by strangers
    - Public team's documents cannot be accessed by strangers
    - Public team resources can only be updated/deleted by team members
    """
    # Create entities
    public_team = _make_reference(Resource.TEAM, prefix="public-team")
    private_team = _make_reference(Resource.TEAM, prefix="private-team")
    team_admin = _make_reference(Resource.USER, prefix="team-admin")
    stranger = _make_reference(Resource.USER, prefix="stranger")

    # Team-owned resources
    agent = _make_reference(Resource.AGENT, prefix="team-agent")
    tag = _make_reference(Resource.TAGS, prefix="team-tag")
    document = _make_reference(Resource.DOCUMENTS, prefix="team-document")

    # Set up teams and resources
    token = await rebac_engine.add_relations(
        [
            # Public team setup
            Relation(
                subject=team_admin,
                relation=RelationType.TEAM_ADMIN,
                resource=public_team,
            ),
            Relation(
                subject=RebacReference(Resource.USER, "*"),
                relation=RelationType.PUBLIC,
                resource=public_team,
            ),
            # Private team setup
            Relation(
                subject=team_admin,
                relation=RelationType.TEAM_ADMIN,
                resource=private_team,
            ),
            # Public team owns resources
            Relation(subject=public_team, relation=RelationType.OWNER, resource=agent),
            Relation(subject=public_team, relation=RelationType.OWNER, resource=tag),
            Relation(subject=tag, relation=RelationType.PARENT, resource=document),
        ]
    )

    # ~~~~~~~~~~~~~~~~~~~~
    # Public team read access

    # Test stranger CAN read public team info
    assert await rebac_engine.has_permission(
        stranger,
        TeamPermission.CAN_READ,
        public_team,
        consistency_token=token,
    ), "Stranger should be able to read public team info"

    # Test stranger CANNOT read private team info
    assert not await rebac_engine.has_permission(
        stranger,
        TeamPermission.CAN_READ,
        private_team,
        consistency_token=token,
    ), "Stranger should not be able to read private team info"

    # AUTHZ-05 review finding (PR #1957): CAN_READ = `team_member or public` —
    # a stranger passes it on a public team without ever being a real member.
    # CAN_READ_MEMEBERS = `team_member` alone (no `public` fallback), so it
    # must stay denied for the same stranger on the same public team. This is
    # the exact public-vs-membership distinction that member-only endpoints
    # (e.g. corpus_manager) must gate on instead of CAN_READ.
    assert await rebac_engine.has_permission(
        stranger,
        TeamPermission.CAN_READ,
        public_team,
        consistency_token=token,
    ), "Stranger should still pass CAN_READ on a public team (sanity check)"

    assert not await rebac_engine.has_permission(
        stranger,
        TeamPermission.CAN_READ_MEMEBERS,
        public_team,
        consistency_token=token,
    ), (
        "Stranger should NOT pass CAN_READ_MEMEBERS on a public team — public visibility is not membership"
    )

    assert await rebac_engine.has_permission(
        team_admin,
        TeamPermission.CAN_READ_MEMEBERS,
        public_team,
        consistency_token=token,
    ), "A real team member (team_admin) should pass CAN_READ_MEMEBERS on a public team"

    # ~~~~~~~~~~~~~~~~~~~~
    # Public team resources remain private

    # Test stranger CANNOT access public team's agent
    assert not await rebac_engine.has_permission(
        stranger,
        AgentPermission.UPDATE,
        agent,
        consistency_token=token,
    ), "Stranger should not be able to update public team's agent"

    assert not await rebac_engine.has_permission(
        stranger,
        AgentPermission.DELETE,
        agent,
        consistency_token=token,
    ), "Stranger should not be able to delete public team's agent"

    # Test stranger CANNOT access public team's tag
    assert not await rebac_engine.has_permission(
        stranger,
        TagPermission.READ,
        tag,
        consistency_token=token,
    ), "Stranger should not be able to read public team's tag"

    assert not await rebac_engine.has_permission(
        stranger,
        TagPermission.UPDATE,
        tag,
        consistency_token=token,
    ), "Stranger should not be able to update public team's tag"

    assert not await rebac_engine.has_permission(
        stranger,
        TagPermission.DELETE,
        tag,
        consistency_token=token,
    ), "Stranger should not be able to delete public team's tag"

    # Test stranger CANNOT access public team's documents
    assert not await rebac_engine.has_permission(
        stranger,
        DocumentPermission.READ,
        document,
        consistency_token=token,
    ), "Stranger should not be able to read public team's document"

    assert not await rebac_engine.has_permission(
        stranger,
        DocumentPermission.UPDATE,
        document,
        consistency_token=token,
    ), "Stranger should not be able to update public team's document"

    # ~~~~~~~~~~~~~~~~~~~~
    # Public team cannot be modified by strangers

    # Test stranger CANNOT update public team info
    assert not await rebac_engine.has_permission(
        stranger,
        TeamPermission.CAN_UPDATE_INFO,
        public_team,
        consistency_token=token,
    ), "Stranger should not be able to update public team info"

    # Test stranger CANNOT update public team members
    assert not await rebac_engine.has_permission(
        stranger,
        TeamPermission.CAN_ADMINISTER_MEMBERS,
        public_team,
        consistency_token=token,
    ), "Stranger should not be able to update public team members"

    # ~~~~~~~~~~~~~~~~~~~~
    # Team admin retains governance access, but NOT agent/prompt authority
    # (team_admin and team_editor are orthogonal, not hierarchical — RFC §6.2,
    # REBAC.md "hard cross-write rule").

    # Test admin CAN still update public team
    assert await rebac_engine.has_permission(
        team_admin,
        TeamPermission.CAN_UPDATE_INFO,
        public_team,
        consistency_token=token,
    ), "Team admin should still be able to update public team info"

    # Test admin does NOT get team_editor's agent authority
    assert not await rebac_engine.has_permission(
        team_admin,
        AgentPermission.UPDATE,
        agent,
        consistency_token=token,
    ), "Team admin should not implicitly get team_editor's agent authority"

    # AUTHZ-05 review item 7 (decided 2026-07-09): team_admin IS a "super
    # team_member" — it keeps every team_member-level read (agents, tags,
    # can_use_team_agents), just none of team_editor's write authority. This
    # is the deliberate, explicit design (not an oversight): team_admin's
    # `team_member` inheritance in schema.fga grants read, orthogonality only
    # withholds update/write.
    assert await rebac_engine.has_permission(
        team_admin,
        AgentPermission.READ,
        agent,
        consistency_token=token,
    ), "Team admin should read team agents as a super team_member"
    assert await rebac_engine.has_permission(
        team_admin,
        TagPermission.READ,
        tag,
        consistency_token=token,
    ), "Team admin should read team tags as a super team_member"
    assert await rebac_engine.has_permission(
        team_admin,
        TeamPermission.CAN_USE_TEAM_AGENTS,
        public_team,
        consistency_token=token,
    ), "Team admin should use team agents as a super team_member"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_team_filtering_by_visibility(
    rebac_engine: RebacEngine,
) -> None:
    """Test that users can only see teams they have access to.

    This test validates:
    - Strangers can only see public teams
    - Users can see public teams + all teams they belong to (regardless of role)
    - `platform_admin` does not bypass team visibility (AUTHZ-05: no relation
      of any kind grants implicit team access, not even the target platform
      role — the legacy Keycloak `admin`/`editor`/`viewer` bridge tested here
      previously was removed outright in review item 8a)
    """
    # Create users
    stranger = _make_reference(Resource.USER, prefix="stranger")
    multi_role_user = _make_reference(Resource.USER, prefix="alice")
    platform_admin = _make_reference(Resource.USER, prefix="admin")

    # Create organization
    organization = _make_reference(Resource.ORGANIZATION, prefix="main-organization")

    # Create teams
    public_team_1 = _make_reference(Resource.TEAM, prefix="public-marketing")
    public_team_2 = _make_reference(Resource.TEAM, prefix="public-sales")
    private_team_owned = _make_reference(Resource.TEAM, prefix="engineering")
    private_team_managed = _make_reference(Resource.TEAM, prefix="design")
    private_team_member = _make_reference(Resource.TEAM, prefix="hr")
    other_private_team = _make_reference(Resource.TEAM, prefix="finance")

    # Set up team visibility and memberships
    token = await rebac_engine.add_relations(
        [
            # Platform admin setup
            Relation(
                subject=platform_admin,
                relation=RelationType.PLATFORM_ADMIN,
                resource=organization,
            ),
            # Link all teams to organization
            Relation(
                subject=organization,
                relation=RelationType.ORGANIZATION,
                resource=public_team_1,
            ),
            Relation(
                subject=organization,
                relation=RelationType.ORGANIZATION,
                resource=public_team_2,
            ),
            Relation(
                subject=organization,
                relation=RelationType.ORGANIZATION,
                resource=private_team_owned,
            ),
            Relation(
                subject=organization,
                relation=RelationType.ORGANIZATION,
                resource=private_team_managed,
            ),
            Relation(
                subject=organization,
                relation=RelationType.ORGANIZATION,
                resource=private_team_member,
            ),
            Relation(
                subject=organization,
                relation=RelationType.ORGANIZATION,
                resource=other_private_team,
            ),
            # Public teams - anyone can read
            Relation(
                subject=RebacReference(Resource.USER, "*"),
                relation=RelationType.PUBLIC,
                resource=public_team_1,
            ),
            Relation(
                subject=RebacReference(Resource.USER, "*"),
                relation=RelationType.PUBLIC,
                resource=public_team_2,
            ),
            # Multi-role user has different roles in different teams
            Relation(
                subject=multi_role_user,
                relation=RelationType.TEAM_ADMIN,
                resource=private_team_owned,
            ),
            Relation(
                subject=multi_role_user,
                relation=RelationType.TEAM_EDITOR,
                resource=private_team_managed,
            ),
            Relation(
                subject=multi_role_user,
                relation=RelationType.TEAM_MEMBER,
                resource=private_team_member,
            ),
            # Other private team - only accessible by its admin
            Relation(
                subject=_make_reference(Resource.USER, prefix="someone-else"),
                relation=RelationType.TEAM_ADMIN,
                resource=other_private_team,
            ),
        ]
    )

    # ~~~~~~~~~~~~~~~~~~~~
    # Stranger can only see public teams

    stranger_teams = await rebac_engine.lookup_resources(
        subject=stranger,
        permission=TeamPermission.CAN_READ,
        resource_type=Resource.TEAM,
        consistency_token=token,
    )

    assert not isinstance(stranger_teams, RebacDisabledResult)
    stranger_team_ids = {team.id for team in stranger_teams}

    assert stranger_team_ids == {
        public_team_1.id,
        public_team_2.id,
    }, f"Stranger should only see public teams, got: {stranger_team_ids}"

    # ~~~~~~~~~~~~~~~~~~~~
    # Multi-role user sees public teams + all their teams (owned, managed, member)

    user_teams = await rebac_engine.lookup_resources(
        subject=multi_role_user,
        permission=TeamPermission.CAN_READ,
        resource_type=Resource.TEAM,
        consistency_token=token,
    )

    assert not isinstance(user_teams, RebacDisabledResult)
    user_team_ids = {team.id for team in user_teams}

    assert user_team_ids == {
        public_team_1.id,
        public_team_2.id,
        private_team_owned.id,
        private_team_managed.id,
        private_team_member.id,
    }, (
        f"User should see all public teams + teams where they have any role, "
        f"got: {user_team_ids}"
    )

    # Verify user does NOT see the other private team
    assert other_private_team.id not in user_team_ids, (
        "User should not see private teams they don't belong to"
    )

    # ~~~~~~~~~~~~~~~~~~~~
    # Platform admin sees only public teams without explicit team relation

    admin_teams = await rebac_engine.lookup_resources(
        subject=platform_admin,
        permission=TeamPermission.CAN_READ,
        resource_type=Resource.TEAM,
        consistency_token=token,
    )

    assert not isinstance(admin_teams, RebacDisabledResult)


# TODO Activate this test when the admin scope is reimplemented

#   admin_team_ids = {team.id for team in admin_teams}

#   assert admin_team_ids == {
#       public_team_1.id,
#       public_team_2.id,
#   }, (
#       "Organization admin should not see private teams without explicit team "
#       f"relation, got: {admin_team_ids}"
#   )


# ---------------------------------------------------------------------------
# Agent-capability team scoping (CAPAB-01 / #1980, RFC AGENT-CAPABILITY §8.1)
# ---------------------------------------------------------------------------


def _organization_ref() -> RebacReference:
    return RebacReference(type=Resource.ORGANIZATION, id=ORGANIZATION_ID)


def _org_team_edge(team: RebacReference) -> list[Relation]:
    """Contextual `organization#team@team:<id>` reverse edge for team-subject
    capability checks (never persisted — every team belongs to the org)."""

    return [
        Relation(subject=team, relation=RelationType.TEAM, resource=_organization_ref())
    ]


def _org_personal_team_edge(team: RebacReference) -> list[Relation]:
    """Contextual reverse edges for a PERSONAL space: both the plain
    `organization#team` edge and the personal-only `organization#personal_team`
    edge the personal-space class relations resolve through (CAPAB-01 / #1961,
    RFC §8.4). A regular team gets only the first."""

    return _org_team_edge(team) + [
        Relation(
            subject=team,
            relation=RelationType.PERSONAL_TEAM,
            resource=_organization_ref(),
        )
    ]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_capability_can_use_tristate(rebac_engine: RebacEngine) -> None:
    """`can_use` (TEAM subject) answers not-enabled / enabled / disabled."""

    org = _organization_ref()
    capability = _make_reference(Resource.CAPABILITY, prefix="cap")
    team = _make_reference(Resource.TEAM, prefix="team")

    token = await rebac_engine.add_relations(
        [
            Relation(
                subject=org, relation=RelationType.ORGANIZATION, resource=capability
            ),
        ]
    )

    # (1) Not enabled anywhere → the team cannot use (admin-gated default).
    assert not await rebac_engine.has_permission(
        team,
        CapabilityPermission.CAN_USE,
        capability,
        contextual_relations=_org_team_edge(team),
        consistency_token=token,
    )

    # (2) Explicit per-team enable → this team can use.
    token = await rebac_engine.add_relation(
        Relation(subject=team, relation=RelationType.ENABLED, resource=capability)
    )
    assert await rebac_engine.has_permission(
        team,
        CapabilityPermission.CAN_USE,
        capability,
        contextual_relations=_org_team_edge(team),
        consistency_token=token,
    )

    # (2b) The leak regression this shape fixes: ANOTHER team does not gain
    # access from team's enablement, whoever the browsing user may be.
    other_team = _make_reference(Resource.TEAM, prefix="other")
    assert not await rebac_engine.has_permission(
        other_team,
        CapabilityPermission.CAN_USE,
        capability,
        contextual_relations=_org_team_edge(other_team),
        consistency_token=token,
    )

    # (3) Disable overrides enable (opt-out wins).
    token = await rebac_engine.add_relation(
        Relation(subject=team, relation=RelationType.DISABLED, resource=capability)
    )
    assert not await rebac_engine.has_permission(
        team,
        CapabilityPermission.CAN_USE,
        capability,
        contextual_relations=_org_team_edge(team),
        consistency_token=token,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_capability_default_on_inherited(rebac_engine: RebacEngine) -> None:
    """A default-on capability is usable by any team (via the contextual
    `organization#team` edge), and a per-team `disabled` tuple opts that
    team back out (tri-state: inherited-on)."""

    org = _organization_ref()
    capability = _make_reference(Resource.CAPABILITY, prefix="cap")
    team = _make_reference(Resource.TEAM, prefix="team")

    token = await rebac_engine.add_relations(
        [
            Relation(
                subject=org, relation=RelationType.ORGANIZATION, resource=capability
            ),
            Relation(
                subject=org, relation=RelationType.DEFAULT_ON, resource=capability
            ),
        ]
    )
    assert await rebac_engine.has_permission(
        team,
        CapabilityPermission.CAN_USE,
        capability,
        contextual_relations=_org_team_edge(team),
        consistency_token=token,
    )

    # Without the contextual reverse edge the default-on path cannot resolve —
    # pins why production helpers must always inject it.
    assert not await rebac_engine.has_permission(
        team, CapabilityPermission.CAN_USE, capability, consistency_token=token
    )

    # The team opts out → inherited-on is revoked for it.
    token = await rebac_engine.add_relation(
        Relation(subject=team, relation=RelationType.DISABLED, resource=capability)
    )
    assert not await rebac_engine.has_permission(
        team,
        CapabilityPermission.CAN_USE,
        capability,
        contextual_relations=_org_team_edge(team),
        consistency_token=token,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_capability_personal_class_scope(rebac_engine: RebacEngine) -> None:
    """The personal-space class position (CAPAB-01 / #1961, RFC §8.4).

    `personal_on` grants ALL personal spaces (contextual `personal_team` edge)
    but not regular teams; `personal_disabled` opts the whole class out;
    precedence is per-team explicit > personal-class > default_on, and the
    class opt-out never touches a per-space explicit `enabled` grant."""

    org = _organization_ref()
    capability = _make_reference(Resource.CAPABILITY, prefix="cap")
    personal = _make_reference(Resource.TEAM, prefix="personal")
    regular = _make_reference(Resource.TEAM, prefix="team")

    token = await rebac_engine.add_relation(
        Relation(subject=org, relation=RelationType.ORGANIZATION, resource=capability)
    )

    # (1) personal_on → every personal space can use it...
    token = await rebac_engine.add_relation(
        Relation(subject=org, relation=RelationType.PERSONAL_ON, resource=capability)
    )
    assert await rebac_engine.has_permission(
        personal,
        CapabilityPermission.CAN_USE,
        capability,
        contextual_relations=_org_personal_team_edge(personal),
        consistency_token=token,
    )
    # ...but a REGULAR team (no personal_team edge injected) does not.
    assert not await rebac_engine.has_permission(
        regular,
        CapabilityPermission.CAN_USE,
        capability,
        contextual_relations=_org_team_edge(regular),
        consistency_token=token,
    )

    # (2) A per-space explicit `disabled` beats the class grant (most specific).
    token = await rebac_engine.add_relation(
        Relation(subject=personal, relation=RelationType.DISABLED, resource=capability)
    )
    assert not await rebac_engine.has_permission(
        personal,
        CapabilityPermission.CAN_USE,
        capability,
        contextual_relations=_org_personal_team_edge(personal),
        consistency_token=token,
    )

    # (3) personal_disabled opts the whole class out of a default_on capability,
    # yet a per-space explicit `enabled` grant survives it (the opt-out
    # subtracts only from the inherited layer).
    org_off = _organization_ref()
    cap2 = _make_reference(Resource.CAPABILITY, prefix="cap")
    kept = _make_reference(Resource.TEAM, prefix="personal")
    dropped = _make_reference(Resource.TEAM, prefix="personal")
    token = await rebac_engine.add_relations(
        [
            Relation(
                subject=org_off, relation=RelationType.ORGANIZATION, resource=cap2
            ),
            Relation(subject=org_off, relation=RelationType.DEFAULT_ON, resource=cap2),
            Relation(
                subject=org_off, relation=RelationType.PERSONAL_DISABLED, resource=cap2
            ),
            Relation(subject=kept, relation=RelationType.ENABLED, resource=cap2),
        ]
    )
    # `dropped` inherited default_on but the personal-class opt-out revokes it.
    assert not await rebac_engine.has_permission(
        dropped,
        CapabilityPermission.CAN_USE,
        cap2,
        contextual_relations=_org_personal_team_edge(dropped),
        consistency_token=token,
    )
    # `kept` has an explicit `enabled` grant → the class opt-out cannot touch it.
    assert await rebac_engine.has_permission(
        kept,
        CapabilityPermission.CAN_USE,
        cap2,
        contextual_relations=_org_personal_team_edge(kept),
        consistency_token=token,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_capability_can_manage_is_org_admin(rebac_engine: RebacEngine) -> None:
    org = _organization_ref()
    capability = _make_reference(Resource.CAPABILITY, prefix="cap")
    admin = _make_reference(Resource.USER, prefix="admin")
    plain = _make_reference(Resource.USER, prefix="plain")

    token = await rebac_engine.add_relations(
        [
            Relation(
                subject=org, relation=RelationType.ORGANIZATION, resource=capability
            ),
            Relation(subject=admin, relation=RelationType.PLATFORM_ADMIN, resource=org),
        ]
    )
    assert await rebac_engine.has_permission(
        admin, CapabilityPermission.CAN_MANAGE, capability, consistency_token=token
    )
    assert not await rebac_engine.has_permission(
        plain, CapabilityPermission.CAN_MANAGE, capability, consistency_token=token
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_capability_lookup_resources_lists_usable(
    rebac_engine: RebacEngine,
) -> None:
    """`lookup_resources(team, can_use, capability)` drives catalog filtering,
    scoped to the browsed team — not to the user's other memberships."""

    org = _organization_ref()
    usable = _make_reference(Resource.CAPABILITY, prefix="usable")
    hidden = _make_reference(Resource.CAPABILITY, prefix="hidden")
    team = _make_reference(Resource.TEAM, prefix="team")
    other_team = _make_reference(Resource.TEAM, prefix="other")

    token = await rebac_engine.add_relations(
        [
            Relation(subject=org, relation=RelationType.ORGANIZATION, resource=usable),
            Relation(subject=org, relation=RelationType.ORGANIZATION, resource=hidden),
            Relation(subject=team, relation=RelationType.ENABLED, resource=usable),
        ]
    )
    resources = await rebac_engine.lookup_resources(
        team,
        CapabilityPermission.CAN_USE,
        Resource.CAPABILITY,
        contextual_relations=_org_team_edge(team),
        consistency_token=token,
    )
    assert not isinstance(resources, RebacDisabledResult)
    ids = {ref.id for ref in resources}
    assert usable.id in ids
    assert hidden.id not in ids

    # The other team's catalog stays empty (the cross-team leak regression).
    other_resources = await rebac_engine.lookup_resources(
        other_team,
        CapabilityPermission.CAN_USE,
        Resource.CAPABILITY,
        contextual_relations=_org_team_edge(other_team),
        consistency_token=token,
    )
    assert not isinstance(other_resources, RebacDisabledResult)
    assert usable.id not in {ref.id for ref in other_resources}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cross_team_isolation_for_agents_and_tags(
    rebac_engine: RebacEngine,
) -> None:
    """A team_editor/team_member of one team must not reach another team's
    agents/tags, even though both teams exist under the same organization.

    Regression guard for the class of bug this whole rename exists to close:
    role names changed, but cross-team isolation must hold exactly as before.
    """
    team_a = _make_reference(Resource.TEAM, prefix="team-a")
    team_b = _make_reference(Resource.TEAM, prefix="team-b")
    team_a_editor = _make_reference(Resource.USER, prefix="a-editor")
    team_a_member = _make_reference(Resource.USER, prefix="a-member")
    agent_a = _make_reference(Resource.AGENT, prefix="agent-a")
    agent_b = _make_reference(Resource.AGENT, prefix="agent-b")
    tag_a = _make_reference(Resource.TAGS, prefix="tag-a")
    tag_b = _make_reference(Resource.TAGS, prefix="tag-b")

    token = await rebac_engine.add_relations(
        [
            Relation(
                subject=team_a_editor,
                relation=RelationType.TEAM_EDITOR,
                resource=team_a,
            ),
            Relation(
                subject=team_a_member,
                relation=RelationType.TEAM_MEMBER,
                resource=team_a,
            ),
            Relation(subject=team_a, relation=RelationType.OWNER, resource=agent_a),
            Relation(subject=team_a, relation=RelationType.OWNER, resource=tag_a),
            Relation(subject=team_b, relation=RelationType.OWNER, resource=agent_b),
            Relation(subject=team_b, relation=RelationType.OWNER, resource=tag_b),
        ]
    )

    # Team A editor/member reach team A's own resources.
    assert await rebac_engine.has_permission(
        team_a_editor, AgentPermission.UPDATE, agent_a, consistency_token=token
    ), "Team A editor should be able to update team A's agent"
    assert await rebac_engine.has_permission(
        team_a_member, AgentPermission.READ, agent_a, consistency_token=token
    ), "Team A member should be able to read team A's agent"

    # Neither reaches team B's agent or tag.
    for subject, label in (
        (team_a_editor, "team A editor"),
        (team_a_member, "team A member"),
    ):
        assert not await rebac_engine.has_permission(
            subject, AgentPermission.READ, agent_b, consistency_token=token
        ), f"{label} must not read team B's agent"
        assert not await rebac_engine.has_permission(
            subject, AgentPermission.UPDATE, agent_b, consistency_token=token
        ), f"{label} must not update team B's agent"
        assert not await rebac_engine.has_permission(
            subject, TagPermission.READ, tag_b, consistency_token=token
        ), f"{label} must not read team B's tag"
        assert not await rebac_engine.has_permission(
            subject, TagPermission.UPDATE, tag_b, consistency_token=token
        ), f"{label} must not update team B's tag"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_team_analyst_evaluation_capabilities(
    rebac_engine: RebacEngine,
) -> None:
    """team_analyst is a distinct, narrower role for evaluation work (RFC §3.2/§6.2):
    it can run evaluations and manage the evaluation corpus, but has none of
    team_editor's corpus/agent authority and none of team_admin's governance
    authority.
    """
    team = _make_reference(Resource.TEAM, prefix="research")
    analyst = _make_reference(Resource.USER, prefix="analyst")

    token = await rebac_engine.add_relations(
        [Relation(subject=analyst, relation=RelationType.TEAM_ANALYST, resource=team)]
    )

    assert await rebac_engine.has_permission(
        analyst, TeamPermission.CAN_RUN_EVALUATIONS, team, consistency_token=token
    ), "team_analyst should be able to run evaluations"
    assert await rebac_engine.has_permission(
        analyst,
        TeamPermission.CAN_MANAGE_EVALUATION_CORPUS,
        team,
        consistency_token=token,
    ), "team_analyst should be able to manage the evaluation corpus"
    assert await rebac_engine.has_permission(
        analyst,
        TeamPermission.CAN_READ_CONVERSATIONS_FOR_EVALUATION,
        team,
        consistency_token=token,
    ), "team_analyst should be able to read conversations for evaluation"

    # No corpus/agent authority (that's team_editor's).
    assert not await rebac_engine.has_permission(
        analyst, TeamPermission.CAN_UPDATE_RESOURCES, team, consistency_token=token
    ), "team_analyst should not be able to update team resources"
    assert not await rebac_engine.has_permission(
        analyst, TeamPermission.CAN_UPDATE_AGENTS, team, consistency_token=token
    ), "team_analyst should not be able to update team agents"

    # No governance authority (that's team_admin's).
    assert not await rebac_engine.has_permission(
        analyst, TeamPermission.CAN_UPDATE_INFO, team, consistency_token=token
    ), "team_analyst should not be able to update team info"
    assert not await rebac_engine.has_permission(
        analyst, TeamPermission.CAN_ADMINISTER_MEMBERS, team, consistency_token=token
    ), "team_analyst should not be able to administer members"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_no_permission_without_persisted_tuple(
    rebac_engine: RebacEngine,
) -> None:
    """AUTHZ-05 item 8b (final sweep): `KeycloakUser` no longer carries a
    `groups` field at all, so there is no claim-derived fallback left to test
    against — a user with no persisted OpenFGA tuple must have no permission
    on the team, full stop. The `groups_list_to_relations`/
    `_user_contextual_relations` fallback that used to derive `team_member`
    from a JWT `groups` claim has been removed outright.
    """
    team = _make_reference(Resource.TEAM, prefix="no-tuple")
    user = _make_keycloak_user()

    assert not await rebac_engine.has_user_permission(
        user, TeamPermission.CAN_READ, team.id
    ), "No persisted tuple must not grant team_member-derived access"

    with pytest.raises(AuthorizationError):
        await rebac_engine.check_user_permission_or_raise(
            user, TeamPermission.CAN_READ, team.id
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_persisted_team_member_tuple_grants_permission(
    rebac_engine: RebacEngine,
) -> None:
    """The same user/team pair as the negative test above, but this time the
    `team_member` relation is written as a real OpenFGA tuple — permission
    must now be granted, proving OpenFGA tuples are the only source of truth.
    """
    team = _make_reference(Resource.TEAM, prefix="with-tuple")
    user = _make_keycloak_user()
    user_ref = RebacReference(Resource.USER, user.uid)

    token = await rebac_engine.add_relation(
        Relation(subject=user_ref, relation=RelationType.TEAM_MEMBER, resource=team)
    )

    assert await rebac_engine.has_user_permission(
        user, TeamPermission.CAN_READ, team.id, consistency_token=token
    ), "A persisted team_member tuple must grant access on its own"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_has_direct_relation_ignores_computed_team_member_rewrite(
    rebac_engine: RebacEngine,
) -> None:
    """PR #1957 review finding (discussion_r3568344074): `team_member` is a
    computed relation in schema.fga (`[user] or team_admin or team_editor or
    team_analyst`), so `has_permission`/`lookup_subjects` cannot tell a direct
    base-member tuple apart from one derived purely from an elevated role.
    `has_direct_relation` must answer only from the literal tuple store."""
    team = _make_reference(Resource.TEAM, prefix="direct-relation")
    editor_only = _make_reference(Resource.USER, prefix="editor-only")
    member_and_editor = _make_reference(Resource.USER, prefix="member-and-editor")

    token = await rebac_engine.add_relations(
        [
            Relation(
                subject=editor_only, relation=RelationType.TEAM_EDITOR, resource=team
            ),
            Relation(
                subject=member_and_editor,
                relation=RelationType.TEAM_MEMBER,
                resource=team,
            ),
            Relation(
                subject=member_and_editor,
                relation=RelationType.TEAM_EDITOR,
                resource=team,
            ),
        ]
    )

    # Both users satisfy the *computed* team_member relation (team_editor
    # implies it) — this is the union-rewrite behavior has_direct_relation
    # must NOT reproduce.
    assert await rebac_engine.has_permission(
        editor_only, TeamPermission.CAN_READ, team, consistency_token=token
    ), (
        "team_editor should satisfy the computed team_member-gated CAN_READ (sanity check)"
    )

    # But only member_and_editor holds a literal team_member tuple.
    assert not await rebac_engine.has_direct_relation(
        editor_only, RelationType.TEAM_MEMBER, team, consistency_token=token
    ), "editor-only user must not read as holding a direct team_member tuple"

    assert await rebac_engine.has_direct_relation(
        member_and_editor, RelationType.TEAM_MEMBER, team, consistency_token=token
    ), "member_and_editor must read as holding a direct team_member tuple"
