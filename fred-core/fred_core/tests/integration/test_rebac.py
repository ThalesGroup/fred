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
    DocumentPermission,
    OpenFgaRebacConfig,
    OpenFgaRebacEngine,
    RebacDisabledResult,
    RebacEngine,
    RebacReference,
    Relation,
    RelationType,
    Resource,
    TagPermission,
    TeamPermission,
)
from fred_core.security.structure import M2MSecurity

MAX_STARTUP_ATTEMPTS = 40
STARTUP_BACKOFF_SECONDS = 0.5


def _integration_token() -> str:
    return f"itest-{uuid.uuid4().hex}"


def _unique_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _make_reference(resource: Resource, *, prefix: str | None = None) -> RebacReference:
    identifier = prefix or resource.value
    return RebacReference(type=resource, id=_unique_id(identifier))


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
        engine = OpenFgaRebacEngine(config, mock_m2m, token=store)
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
async def test_list_relations_filters_by_subject_type(
    rebac_engine: RebacEngine,
) -> None:
    if not rebac_engine.need_keycloak_sync:
        pytest.skip(
            "Keycloak sync not needed for this backend, list_relations not needed and not implemented"
        )

    team = _make_reference(Resource.TEAM, prefix="team")
    child_team = _make_reference(Resource.TEAM, prefix="team")
    member = _make_reference(Resource.USER, prefix="member")

    token = await rebac_engine.add_relations(
        [
            Relation(subject=member, relation=RelationType.MEMBER, resource=team),
            Relation(subject=team, relation=RelationType.MEMBER, resource=child_team),
        ]
    )

    user_memberships = await rebac_engine.list_relations(
        resource_type=Resource.TEAM,
        relation=RelationType.MEMBER,
        subject_type=Resource.USER,
        consistency_token=token,
    )
    group_memberships = await rebac_engine.list_relations(
        resource_type=Resource.TEAM,
        relation=RelationType.MEMBER,
        subject_type=Resource.TEAM,
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
    } == {(Resource.TEAM, team.id, child_team.id)}


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
    """Test team ownership, management, and permission inheritance.

    This test validates:
    - Team owner can update team info
    - Team manager can update members
    - Team members inherit permissions from team roles on tags and agents
    - Platform admins inherit team ownership
    """
    # Create entities
    platform = _make_reference(Resource.PLATFORM, prefix="platform")
    platform_admin = _make_reference(Resource.USER, prefix="admin")
    team = _make_reference(Resource.TEAM, prefix="marketing")
    team_owner = _make_reference(Resource.USER, prefix="owner")
    team_manager = _make_reference(Resource.USER, prefix="manager")
    team_member = _make_reference(Resource.USER, prefix="member")
    tag = _make_reference(Resource.TAGS, prefix="docs")
    agent = _make_reference(Resource.AGENT, prefix="assistant")

    # Set up team hierarchy and relations
    token = await rebac_engine.add_relations(
        [
            # Platform admin
            Relation(
                subject=platform_admin, relation=RelationType.ADMIN, resource=platform
            ),
            # Team hierarchy - team has a platform reference
            Relation(subject=platform, relation=RelationType.PLATFORM, resource=team),
            Relation(subject=team_owner, relation=RelationType.OWNER, resource=team),
            Relation(
                subject=team_manager, relation=RelationType.MANAGER, resource=team
            ),
            Relation(subject=team_member, relation=RelationType.MEMBER, resource=team),
            # Team owns tag and agent
            Relation(subject=team, relation=RelationType.OWNER, resource=tag),
            Relation(subject=team, relation=RelationType.OWNER, resource=agent),
        ]
    )

    # ~~~~~~~~~~~~~~~~~~~~
    # Owner

    # Test owner can update team info
    assert await rebac_engine.has_permission(
        team_owner,
        TeamPermission.CAN_UPDATE_INFO,
        team,
        consistency_token=token,
    ), "Team owner should be able to update team info"

    # ~~~~~~~~~~~~~~~~~~~~
    # Manager

    # Test manager can update members
    assert await rebac_engine.has_permission(
        team_manager,
        TeamPermission.CAN_UPDATE_MEMBERS,
        team,
        consistency_token=token,
    ), "Team manager should be able to update members"

    # Test manager can update tag via team ownership
    assert await rebac_engine.has_permission(
        team_manager,
        TagPermission.UPDATE,
        tag,
        consistency_token=token,
    ), "Team manager should be able to update team tag"

    # Test manager can update agent via team ownership
    assert await rebac_engine.has_permission(
        team_manager,
        AgentPermission.UPDATE,
        agent,
        consistency_token=token,
    ), "Team manager should be able to update team agent"

    # Test owner can update team info
    assert not await rebac_engine.has_permission(
        team_manager,
        TeamPermission.CAN_UPDATE_INFO,
        team,
        consistency_token=token,
    ), "Team manager should not be able to update team info"

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

    # ~~~~~~~~~~~~~~~~~~~~
    # Platform admin

    # Test platform admin can edit team info
    assert await rebac_engine.has_permission(
        platform_admin,
        TeamPermission.CAN_UPDATE_INFO,
        team,
        consistency_token=token,
    ), "Platform admin should be able to update team info"

    # Test platform admin can edit team info
    assert await rebac_engine.has_permission(
        platform_admin,
        TeamPermission.CAN_UPDATE_MEMBERS,
        team,
        consistency_token=token,
    ), "Platform admin should be able to update team members"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_team_tag_document_hierarchy(
    rebac_engine: RebacEngine,
) -> None:
    """Test that team permissions cascade through tag/document hierarchy.

    This test validates:
    - Team manager can update tags owned by team
    - Documents inherit permissions from parent tags
    - Nested tags inherit permissions correctly
    """
    team = _make_reference(Resource.TEAM, prefix="engineering")
    manager = _make_reference(Resource.USER, prefix="manager")
    member = _make_reference(Resource.USER, prefix="member")
    root_tag = _make_reference(Resource.TAGS, prefix="root")
    sub_tag = _make_reference(Resource.TAGS, prefix="subtag")
    document = _make_reference(Resource.DOCUMENTS, prefix="document")

    token = await rebac_engine.add_relations(
        [
            # Team structure
            Relation(subject=manager, relation=RelationType.MANAGER, resource=team),
            Relation(subject=member, relation=RelationType.MEMBER, resource=team),
            # Tag hierarchy
            Relation(subject=team, relation=RelationType.OWNER, resource=root_tag),
            Relation(subject=root_tag, relation=RelationType.PARENT, resource=sub_tag),
            Relation(subject=sub_tag, relation=RelationType.PARENT, resource=document),
        ]
    )

    # Test manager can update root tag via team permission
    assert await rebac_engine.has_permission(
        manager,
        TagPermission.UPDATE,
        root_tag,
        consistency_token=token,
    ), "Team manager should be able to update team tag"

    # Test manager can delete subtag via parent tag permission
    assert await rebac_engine.has_permission(
        manager,
        TagPermission.DELETE,
        sub_tag,
        consistency_token=token,
    ), "Team manager should be able to delete subtag"

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

    # Test manager can update document via tag hierarchy
    assert await rebac_engine.has_permission(
        manager,
        DocumentPermission.UPDATE,
        document,
        consistency_token=token,
    ), "Team manager should be able to update document in team tag"


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
    team_owner = _make_reference(Resource.USER, prefix="owner")
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
                subject=team_owner, relation=RelationType.OWNER, resource=public_team
            ),
            Relation(
                subject=RebacReference(Resource.USER, "*"),
                relation=RelationType.PUBLIC,
                resource=public_team,
            ),
            # Private team setup
            Relation(
                subject=team_owner, relation=RelationType.OWNER, resource=private_team
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
        TeamPermission.CAN_UPDATE_MEMBERS,
        public_team,
        consistency_token=token,
    ), "Stranger should not be able to update public team members"

    # ~~~~~~~~~~~~~~~~~~~~
    # Team owner retains full access

    # Test owner CAN still update public team
    assert await rebac_engine.has_permission(
        team_owner,
        TeamPermission.CAN_UPDATE_INFO,
        public_team,
        consistency_token=token,
    ), "Team owner should still be able to update public team info"

    # Test owner CAN access team resources
    assert await rebac_engine.has_permission(
        team_owner,
        AgentPermission.UPDATE,
        agent,
        consistency_token=token,
    ), "Team owner should be able to update public team agent"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_team_filtering_by_visibility(
    rebac_engine: RebacEngine,
) -> None:
    """Test that users can only see teams they have access to.

    This test validates:
    - Strangers can only see public teams
    - Users can see public teams + all teams they belong to (regardless of role)
    - Platform admins can see all teams (public and private)
    """
    # Create users
    stranger = _make_reference(Resource.USER, prefix="stranger")
    multi_role_user = _make_reference(Resource.USER, prefix="alice")
    platform_admin = _make_reference(Resource.USER, prefix="admin")

    # Create platform
    platform = _make_reference(Resource.PLATFORM, prefix="main-platform")

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
                relation=RelationType.ADMIN,
                resource=platform,
            ),
            # Link all teams to platform
            Relation(
                subject=platform, relation=RelationType.PLATFORM, resource=public_team_1
            ),
            Relation(
                subject=platform, relation=RelationType.PLATFORM, resource=public_team_2
            ),
            Relation(
                subject=platform,
                relation=RelationType.PLATFORM,
                resource=private_team_owned,
            ),
            Relation(
                subject=platform,
                relation=RelationType.PLATFORM,
                resource=private_team_managed,
            ),
            Relation(
                subject=platform,
                relation=RelationType.PLATFORM,
                resource=private_team_member,
            ),
            Relation(
                subject=platform,
                relation=RelationType.PLATFORM,
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
                relation=RelationType.OWNER,
                resource=private_team_owned,
            ),
            Relation(
                subject=multi_role_user,
                relation=RelationType.MANAGER,
                resource=private_team_managed,
            ),
            Relation(
                subject=multi_role_user,
                relation=RelationType.MEMBER,
                resource=private_team_member,
            ),
            # Other private team - only accessible by platform admin and its owner
            Relation(
                subject=_make_reference(Resource.USER, prefix="someone-else"),
                relation=RelationType.OWNER,
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
    # Platform admin sees ALL teams (public and private)

    admin_teams = await rebac_engine.lookup_resources(
        subject=platform_admin,
        permission=TeamPermission.CAN_READ,
        resource_type=Resource.TEAM,
        consistency_token=token,
    )

    assert not isinstance(admin_teams, RebacDisabledResult)
    admin_team_ids = {team.id for team in admin_teams}

    assert admin_team_ids == {
        public_team_1.id,
        public_team_2.id,
        private_team_owned.id,
        private_team_managed.id,
        private_team_member.id,
        other_private_team.id,
    }, (
        f"Platform admin should see all teams (public and private), "
        f"got: {admin_team_ids}"
    )
