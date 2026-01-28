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
    FilePermission,
    FolderPermission,
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_team_hierarchy_and_permissions(
    rebac_engine: RebacEngine,
) -> None:
    """Test team ownership, management, and permission inheritance.

    This test validates:
    - Team owner can update team info
    - Team manager can update members
    - Team members inherit permissions from team roles on folders and agents
    - Platform admins inherit team ownership
    """
    # Create entities
    platform = _make_reference(Resource.PLATFORM, prefix="platform")
    platform_admin = _make_reference(Resource.USER, prefix="admin")
    team = _make_reference(Resource.TEAM, prefix="marketing")
    team_owner = _make_reference(Resource.USER, prefix="owner")
    team_manager = _make_reference(Resource.USER, prefix="manager")
    team_member = _make_reference(Resource.USER, prefix="member")
    folder = _make_reference(Resource.FOLDER, prefix="docs")
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
            # Team owns folder and agent
            Relation(subject=team, relation=RelationType.OWNER, resource=folder),
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

    # Test manager can update folder via team ownership
    assert await rebac_engine.has_permission(
        team_manager,
        FolderPermission.UPDATE,
        folder,
        consistency_token=token,
    ), "Team manager should be able to update team folder"

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

    # Test members can access team-owned folders
    assert await rebac_engine.has_permission(
        team_member,
        FolderPermission.READ,
        folder,
        consistency_token=token,
    ), "Team member should be able to read team folder"

    # Test regular member cannot update team info
    assert not await rebac_engine.has_permission(
        team_member,
        TeamPermission.CAN_UPDATE_INFO,
        team,
        consistency_token=token,
    ), "Team member should not be able to update team info"

    # Test member cannot update folder (needs at least editor role)
    assert not await rebac_engine.has_permission(
        team_member,
        FolderPermission.UPDATE,
        folder,
        consistency_token=token,
    ), "Team member should not be able to update folder"

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
async def test_team_folder_file_hierarchy(
    rebac_engine: RebacEngine,
) -> None:
    """Test that team permissions cascade through folder/file hierarchy.

    This test validates:
    - Team manager can update folders owned by team
    - Files inherit permissions from parent folders
    - Nested folders inherit permissions correctly
    """
    team = _make_reference(Resource.TEAM, prefix="engineering")
    manager = _make_reference(Resource.USER, prefix="manager")
    member = _make_reference(Resource.USER, prefix="member")
    root_folder = _make_reference(Resource.FOLDER, prefix="root")
    sub_folder = _make_reference(Resource.FOLDER, prefix="subfolder")
    file = _make_reference(Resource.FILE, prefix="document")

    token = await rebac_engine.add_relations(
        [
            # Team structure
            Relation(subject=manager, relation=RelationType.MANAGER, resource=team),
            Relation(subject=member, relation=RelationType.MEMBER, resource=team),
            # Folder hierarchy
            Relation(subject=team, relation=RelationType.OWNER, resource=root_folder),
            Relation(
                subject=root_folder, relation=RelationType.PARENT, resource=sub_folder
            ),
            Relation(subject=sub_folder, relation=RelationType.PARENT, resource=file),
        ]
    )

    # Test manager can update root folder via team permission
    assert await rebac_engine.has_permission(
        manager,
        FolderPermission.UPDATE,
        root_folder,
        consistency_token=token,
    ), "Team manager should be able to update team folder"

    # Test manager can delete subfolder via parent folder permission
    assert await rebac_engine.has_permission(
        manager,
        FolderPermission.DELETE,
        sub_folder,
        consistency_token=token,
    ), "Team manager should be able to delete subfolder"

    # Test member can read file through folder hierarchy
    assert await rebac_engine.has_permission(
        member,
        FilePermission.READ,
        file,
        consistency_token=token,
    ), "Team member should be able to read file in team folder"

    # Test member cannot update file (needs at least editor role)
    assert not await rebac_engine.has_permission(
        member,
        FilePermission.UPDATE,
        file,
        consistency_token=token,
    ), "Team member should not be able to update file (needs editor role)"

    # Test manager can update file via folder hierarchy
    assert await rebac_engine.has_permission(
        manager,
        FilePermission.UPDATE,
        file,
        consistency_token=token,
    ), "Team manager should be able to update file in team folder"


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
    - Public team's folders cannot be accessed by strangers
    - Public team's files cannot be accessed by strangers
    - Public team resources can only be updated/deleted by team members
    """
    # Create entities
    public_team = _make_reference(Resource.TEAM, prefix="public-team")
    private_team = _make_reference(Resource.TEAM, prefix="private-team")
    team_owner = _make_reference(Resource.USER, prefix="owner")
    stranger = _make_reference(Resource.USER, prefix="stranger")

    # Team-owned resources
    agent = _make_reference(Resource.AGENT, prefix="team-agent")
    folder = _make_reference(Resource.FOLDER, prefix="team-folder")
    file = _make_reference(Resource.FILE, prefix="team-file")

    # Set up teams and resources
    token = await rebac_engine.add_relations(
        [
            # Public team setup
            Relation(subject=team_owner, relation=RelationType.OWNER, resource=public_team),
            Relation(
                subject=RebacReference(Resource.USER, "*"),
                relation=RelationType.PUBLIC,
                resource=public_team,
            ),
            # Private team setup
            Relation(subject=team_owner, relation=RelationType.OWNER, resource=private_team),
            # Public team owns resources
            Relation(subject=public_team, relation=RelationType.OWNER, resource=agent),
            Relation(subject=public_team, relation=RelationType.OWNER, resource=folder),
            Relation(subject=folder, relation=RelationType.PARENT, resource=file),
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

    # Test stranger CANNOT access public team's folder
    assert not await rebac_engine.has_permission(
        stranger,
        FolderPermission.READ,
        folder,
        consistency_token=token,
    ), "Stranger should not be able to read public team's folder"

    assert not await rebac_engine.has_permission(
        stranger,
        FolderPermission.UPDATE,
        folder,
        consistency_token=token,
    ), "Stranger should not be able to update public team's folder"

    assert not await rebac_engine.has_permission(
        stranger,
        FolderPermission.DELETE,
        folder,
        consistency_token=token,
    ), "Stranger should not be able to delete public team's folder"

    # Test stranger CANNOT access public team's files
    assert not await rebac_engine.has_permission(
        stranger,
        FilePermission.READ,
        file,
        consistency_token=token,
    ), "Stranger should not be able to read public team's file"

    assert not await rebac_engine.has_permission(
        stranger,
        FilePermission.UPDATE,
        file,
        consistency_token=token,
    ), "Stranger should not be able to update public team's file"

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
