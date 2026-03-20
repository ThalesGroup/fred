from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from fred_core.security.keycloak.keycloack_admin_client import (
    KeycloackDisabled,
    create_keycloak_admin,
)
from fred_core.security.models import AuthorizationError, Resource
from fred_core.security.structure import KeycloakUser, M2MSecurity

ORGANIZATION_ID = "fred"
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RebacReference:
    """Point to one actor or object in authorization checks.

    Example:
    - `RebacReference(Resource.USER, "alice-id")`
    - `RebacReference(Resource.TEAM, "thales-team-id")`
    """

    type: Resource
    id: str


class RelationType(str, Enum):
    """Named links used to describe who can do what.

    Example:
    - `owner`: full control on an entity.
    - `manager`: can manage team content.
    - `member`: can access team-scoped reads.
    """

    OWNER = "owner"
    MANAGER = "manager"
    EDITOR = "editor"
    VIEWER = "viewer"
    PARENT = "parent"
    MEMBER = "member"
    ORGANIZATION = "organization"
    ADMIN = "admin"
    PUBLIC = "public"


class TagPermission(str, Enum):
    """Actions allowed on libraries/tags.

    Example:
    - `read`: list/search content.
    - `update`: rename tag, edit metadata, attach resources.
    """

    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    SHARE = "share"

    # Normaly those 3 are "relation" and not "permission"
    # but openfga does not make distinction so we added
    # them here to use lookup_resources on them
    OWNER = RelationType.OWNER.value
    EDITOR = RelationType.EDITOR.value
    VIEWER = RelationType.VIEWER.value


class DocumentPermission(str, Enum):
    """Actions allowed on documents stored in libraries."""

    READ = "read"
    UPDATE = "update"
    DELETE = "delete"


class ResourcePermission(str, Enum):
    """Actions allowed on non-document resources (files, templates, etc.)."""

    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    SHARE = "share"


class TeamPermission(str, Enum):
    """Actions allowed at team scope.

    Example:
    - `can_update_resources`: create/update team libraries.
    - `can_administer_members`: add/remove team members.
    """

    CAN_READ = "can_read"
    CAN_UPDATE_INFO = "can_update_info"
    CAN_UPDATE_RESOURCES = "can_update_resources"
    CAN_UPDATE_AGENTS = "can_update_agents"
    CAN_READ_MEMEBERS = "can_read_members"
    CAN_ADMINISTER_MEMBERS = "can_administer_members"
    CAN_ADMINISTER_MANAGERS = "can_administer_managers"
    CAN_ADMINISTER_OWNERS = "can_administer_owners"


class AgentPermission(str, Enum):
    """Actions allowed on agents."""

    READ = "read"
    UPDATE = "update"
    DELETE = "delete"

    # "owner" is a relation in the FGA schema, not a permission,
    # but openfga does not make distinction so we add it here
    # to use lookup_resources on it (for owner-based filtering).
    OWNER = RelationType.OWNER.value


class OrganizationPermission(str, Enum):
    """Actions allowed at global organization scope."""

    CAN_EDIT_AGENT_CLASS_PATH = "can_edit_agent_class_path"


RebacPermission = (
    TagPermission
    | DocumentPermission
    | ResourcePermission
    | TeamPermission
    | AgentPermission
    | OrganizationPermission
)


def _resource_for_permission(permission: RebacPermission) -> Resource:
    """Map one permission enum value to the resource type it targets.

    Example:
    - `TeamPermission.CAN_READ` -> `Resource.TEAM`
    - `TagPermission.UPDATE` -> `Resource.TAGS`
    """
    if isinstance(permission, TagPermission):
        return Resource.TAGS
    if isinstance(permission, DocumentPermission):
        return Resource.DOCUMENTS
    if isinstance(permission, ResourcePermission):
        return Resource.RESOURCES
    if isinstance(permission, TeamPermission):
        return Resource.TEAM
    if isinstance(permission, AgentPermission):
        return Resource.AGENT
    if isinstance(permission, OrganizationPermission):
        return Resource.ORGANIZATION
    raise ValueError(f"Unsupported permission type: {permission!r}")


@dataclass(frozen=True)
class Relation:
    """One authorization statement linking an actor to a target.

    Example:
    - `user alice` `owner` of `tag invoices`
    - `team thales` `owner` of `tag cir`
    """

    subject: RebacReference
    relation: RelationType
    resource: RebacReference


class RebacDisabledResult:
    """
    Marker object returned when relationship authorization is disabled.

    Callers can branch on this value and apply fallback behavior.
    """

    ...


class RebacEngine(ABC):
    """Core authorization API used by all Fred backends.

    This class provides the common business operations ("can Alice update team
    resources?") while each concrete engine (OpenFGA, noop) handles storage.
    """

    def __init__(self, m2m_security: M2MSecurity) -> None:
        """Initialize engine dependencies used for contextual relations."""
        self.keycloak_client = create_keycloak_admin(m2m_security)

    @property
    def enabled(self) -> bool:
        """Tell whether relationship authorization checks are active."""
        return True

    @property
    def need_keycloak_sync(self) -> bool:
        """Tell whether this backend requires periodic Keycloak graph sync."""
        return False

    @abstractmethod
    async def add_relation(self, relation: Relation) -> str | None:
        """Persist one authorization statement.

        Example:
        - Save `team thales owner tag cir`.
        Returns a backend-specific consistency token when available.
        """

    @abstractmethod
    async def delete_relation(self, relation: Relation) -> str | None:
        """Remove one authorization statement.

        Returns a backend-specific consistency token when available.
        """

    @abstractmethod
    async def delete_all_relations_of_reference(
        self, reference: RebacReference
    ) -> str | None:
        """Remove every statement touching the given reference.

        Example:
        - deleting an agent can remove all `owner`, `viewer`, or parent links.
        """

    async def add_relations(self, relations: Iterable[Relation]) -> str | None:
        """Persist several statements and return the latest consistency token.

        Example:
        - Add owner and viewer links in one call after resource sharing.
        """

        tokens = await asyncio.gather(
            *(self.add_relation(relation) for relation in relations),
            return_exceptions=False,
        )

        token: str | None = None
        for t in reversed(tokens):
            if t is not None:
                token = t
                break

        return token

    async def ensure_team_organization_relations(
        self,
        team_ids: Iterable[str],
    ) -> str | None:
        """Ensure each team is linked to the singleton organization.

        Team checks in Fred always operate in a team context and require
        deterministic organization/team graph edges for future policy evolution.
        This helper maintains the persistent relation:
        ``organization:fred#organization@team:<team_id>``.

        Example:
        - Before checking team permissions on `team:<id>`, ensure
          `organization:fred -> team:<id>` exists.

        This helper is idempotent and returns the write consistency token when
        available.
        """
        unique_team_ids: list[str] = []
        seen: set[str] = set()
        for team_id in team_ids:
            if not team_id or team_id in seen:
                continue
            seen.add(team_id)
            unique_team_ids.append(team_id)

        if not unique_team_ids:
            return None

        relations = [
            Relation(
                subject=RebacReference(Resource.ORGANIZATION, ORGANIZATION_ID),
                relation=RelationType.ORGANIZATION,
                resource=RebacReference(Resource.TEAM, team_id),
            )
            for team_id in unique_team_ids
        ]
        return await self.add_relations(relations)

    async def add_user_relation(
        self,
        user: KeycloakUser,
        relation: RelationType,
        resource_type: Resource,
        resource_id: str,
    ) -> str | None:
        """Create one statement where the subject is a user.

        Example:
        - Add `user:bob editor tag:finance`.
        """
        return await self.add_relation(
            Relation(
                subject=RebacReference(Resource.USER, user.uid),
                relation=relation,
                resource=RebacReference(resource_type, resource_id),
            )
        )

    async def delete_relations(self, relations: Iterable[Relation]) -> str | None:
        """Delete several statements and return the latest consistency token.

        Example:
        - Remove owner/manager/member links when removing a team member.
        """
        tokens = await asyncio.gather(
            *(self.delete_relation(relation) for relation in relations),
            return_exceptions=False,
        )

        token: str | None = None
        for t in reversed(tokens):
            if t is not None:
                token = t
                break

        return token

    @abstractmethod
    async def list_relations(
        self,
        *,
        resource_type: Resource,
        relation: RelationType,
        subject_type: Resource | None = None,
        consistency_token: str | None = None,
    ) -> list[Relation] | RebacDisabledResult:
        """List persisted statements matching the given filters."""

    async def delete_user_relation(
        self,
        user: KeycloakUser,
        relation: RelationType,
        resource_type: Resource,
        resource_id: str,
    ) -> str | None:
        """Delete one statement where the subject is a user."""
        return await self.delete_relation(
            Relation(
                subject=RebacReference(Resource.USER, user.uid),
                relation=relation,
                resource=RebacReference(resource_type, resource_id),
            )
        )

    async def delete_user_relations(self, user: KeycloakUser) -> str | None:
        """Delete all statements referencing a user."""
        return await self.delete_all_relations_of_reference(
            RebacReference(Resource.USER, user.uid)
        )

    @abstractmethod
    async def lookup_resources(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource_type: Resource,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> list[RebacReference] | RebacDisabledResult:
        """List resources a subject can access for one permission.

        Example:
        - Return all teams a user can read.
        """

    @abstractmethod
    async def lookup_subjects(
        self,
        resource: RebacReference,
        relation: RelationType,
        subject_type: Resource,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> list[RebacReference] | RebacDisabledResult:
        """List subjects linked to a resource by one relation.

        Example:
        - List all owners of one team.
        """

    async def lookup_user_resources(
        self,
        user: KeycloakUser,
        permission: RebacPermission,
        *,
        consistency_token: str | None = None,
    ) -> list[RebacReference] | RebacDisabledResult:
        """List resources a user can access for one permission."""
        return await self.lookup_resources(
            subject=RebacReference(Resource.USER, user.uid),
            permission=permission,
            resource_type=_resource_for_permission(permission),
            contextual_relations=await self._user_contextual_relations(user),
            consistency_token=consistency_token,
        )

    @abstractmethod
    async def has_permission(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource: RebacReference,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> bool:
        """Return `True` when a subject is authorized for an action."""

    async def has_user_permission(
        self,
        user: KeycloakUser,
        permission: RebacPermission,
        resource_id: str,
        *,
        consistency_token: str | None = None,
    ) -> bool:
        """Check one permission for one user/resource pair."""
        resource_type = _resource_for_permission(permission)
        return await self.has_permission(
            RebacReference(Resource.USER, user.uid),
            permission,
            RebacReference(resource_type, resource_id),
            contextual_relations=await self._user_contextual_relations(user),
            consistency_token=consistency_token,
        )

    async def check_permission_or_raise(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource: RebacReference,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> None:
        """Raise `AuthorizationError` when access is denied.

        Example:
        - Raises if Bob tries to update a team where he is only a member.
        """
        if not await self.has_permission(
            subject,
            permission,
            resource,
            contextual_relations=contextual_relations,
            consistency_token=consistency_token,
        ):
            logger.warning(
                "ReBAC authorization denied: subject=%s:%s permission=%s resource=%s:%s",
                subject.type.value,
                subject.id,
                permission.value,
                resource.type.value,
                resource.id,
            )
            raise AuthorizationError(
                subject.id,
                permission.value,
                resource.type,
                f"Not authorized to {permission.value} {resource.type.value} {resource.id}",
            )

    async def check_user_permission_or_raise(
        self,
        user: KeycloakUser,
        permission: RebacPermission,
        resource_id: str,
        *,
        consistency_token: str | None = None,
    ) -> None:
        """User-focused wrapper around `check_permission_or_raise`."""
        resource_type = _resource_for_permission(permission)
        await self.check_permission_or_raise(
            RebacReference(Resource.USER, user.uid),
            permission,
            RebacReference(resource_type, resource_id),
            contextual_relations=await self._user_contextual_relations(user),
            consistency_token=consistency_token,
        )

    async def check_user_team_permission_or_raise(
        self,
        user: KeycloakUser,
        permission: TeamPermission,
        team_id: str,
    ) -> str | None:
        """Check one team permission with the canonical team workflow.

        This helper always ensures the team is linked to the organization
        before checking permissions.
        """
        return await self.check_user_team_permissions_or_raise(
            user=user,
            team_id=team_id,
            permissions=[permission],
        )

    async def check_user_team_permissions_or_raise(
        self,
        user: KeycloakUser,
        team_id: str,
        permissions: Iterable[TeamPermission],
    ) -> str | None:
        """Check team permissions with consistent organization-team bootstrap.

        This is the canonical path for team permission checks across services.
        It ensures ``organization -> team`` exists, propagates the resulting
        consistency token, and executes all requested checks.
        """
        consistency_token = await self.ensure_team_organization_relations([team_id])

        permissions_to_check = list(permissions)
        if not permissions_to_check:
            return consistency_token

        await asyncio.gather(
            *(
                self.check_user_permission_or_raise(
                    user=user,
                    permission=permission,
                    resource_id=team_id,
                    consistency_token=consistency_token,
                )
                for permission in permissions_to_check
            ),
            return_exceptions=False,
        )
        return consistency_token

    async def _user_contextual_relations(self, user: KeycloakUser) -> set[Relation]:
        """Build contextual statements derived from the current user identity.

        Example:
        - user group memberships -> `member` links
        - global app role -> organization role link
        """
        group_relations, org_relations = await asyncio.gather(
            self.groups_list_to_relations(user),
            self.user_role_to_organization_relation(user),
        )
        return group_relations | org_relations

    async def groups_list_to_relations(self, user: KeycloakUser) -> set[Relation]:
        """Convert token group paths into team membership statements.

        Example:
        - group `/thales` becomes `user -> member -> team:thales`.
        """
        if isinstance(self.keycloak_client, KeycloackDisabled):
            return set()

        relation: set[Relation] = set()

        for group in user.groups:
            relation.add(
                Relation(
                    subject=RebacReference(Resource.USER, user.uid),
                    relation=RelationType.MEMBER,
                    resource=RebacReference(
                        Resource.TEAM,
                        (await self.keycloak_client.a_get_group_by_path(group))["id"],
                    ),
                )
            )

        return relation

    async def user_role_to_organization_relation(
        self, user: KeycloakUser
    ) -> set[Relation]:
        """Convert app roles into organization-level statements.

        Creates a relation between the user and the singleton 'fred' organization
        based on the user's Keycloak role (admin, editor, or viewer).

        Example:
        - role `admin` becomes `user -> admin -> organization:fred`.
        """
        if isinstance(self.keycloak_client, KeycloackDisabled):
            return set()

        relations: set[Relation] = set()

        # Map Keycloak roles to organization relations based on the schema
        for role in user.roles:
            try:
                relation_type = RelationType(role)
                if relation_type in (
                    RelationType.ADMIN,
                    RelationType.EDITOR,
                    RelationType.VIEWER,
                ):
                    relations.add(
                        Relation(
                            subject=RebacReference(Resource.USER, user.uid),
                            relation=relation_type,
                            resource=RebacReference(
                                Resource.ORGANIZATION, ORGANIZATION_ID
                            ),
                        )
                    )
            except ValueError:
                # Role is not a valid RelationType, skip it
                continue

        return relations
