from __future__ import annotations

import asyncio
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


@dataclass(frozen=True)
class RebacReference:
    """Identifies a subject or resource within the authorization graph."""

    type: Resource
    id: str


class RelationType(str, Enum):
    """Relationship labels encoded in the graph."""

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
    """Tag permissions encoded in the graph."""

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
    """Document permissions encoded in the graph."""

    READ = "read"
    UPDATE = "update"
    DELETE = "delete"


class ResourcePermission(str, Enum):
    """Resource permissions encoded in the graph."""

    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    SHARE = "share"


class TeamPermission(str, Enum):
    """Team permissions encoded in the graph."""

    CAN_READ = "can_read"
    CAN_UPDATE_INFO = "can_update_info"
    CAN_UPDATE_RESOURCES = "can_update_resources"
    CAN_UPDATE_AGENTS = "can_update_agents"
    CAN_READ_MEMEBERS = "can_read_members"
    CAN_ADMINISTER_MEMBERS = "can_administer_members"
    CAN_ADMINISTER_MANAGERS = "can_administer_managers"
    CAN_ADMINISTER_OWNERS = "can_administer_owners"


class AgentPermission(str, Enum):
    """Agent permissions encoded in the graph."""

    READ = "read"
    UPDATE = "update"
    DELETE = "delete"

    # "owner" is a relation in the FGA schema, not a permission,
    # but openfga does not make distinction so we add it here
    # to use lookup_resources on it (for owner-based filtering).
    OWNER = RelationType.OWNER.value


class OrganizationPermission(str, Enum):
    """Organization-level permissions encoded in the graph."""

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
    """Edge connecting a subject (holder) to a resource (target)."""

    subject: RebacReference
    relation: RelationType
    resource: RebacReference


class RebacDisabledResult:
    """
    Class used to represent rebac operation result when rebac has been disabled,
    to let know the caller it must handle this case.
    """

    ...


class RebacEngine(ABC):
    """Abstract base for relationship-based authorization providers."""

    def __init__(self, m2m_security: M2MSecurity) -> None:
        self.keycloak_client = create_keycloak_admin(m2m_security)

    @property
    def enabled(self) -> bool:
        return True

    @property
    def need_keycloak_sync(self) -> bool:
        return False

    @abstractmethod
    async def add_relation(self, relation: Relation) -> str | None:
        """Persist a relationship edge into the underlying store.

        Returns a backend-specific consistency token when available.
        """

    @abstractmethod
    async def delete_relation(self, relation: Relation) -> str | None:
        """Remove a relationship edge from the underlying store.

        Returns a backend-specific consistency token when available.
        """

    @abstractmethod
    async def delete_all_relations_of_reference(
        self, reference: RebacReference
    ) -> str | None:
        """Remove all relationships where the reference participates as subject or resource."""

    async def add_relations(self, relations: Iterable[Relation]) -> str | None:
        """Convenience helper to persist multiple relationships.

        Returns the last non-null consistency token produced.
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

    async def add_user_relation(
        self,
        user: KeycloakUser,
        relation: RelationType,
        resource_type: Resource,
        resource_id: str,
    ) -> str | None:
        """Convenience helper to add a relation for a user."""
        return await self.add_relation(
            Relation(
                subject=RebacReference(Resource.USER, user.uid),
                relation=relation,
                resource=RebacReference(resource_type, resource_id),
            )
        )

    async def delete_relations(self, relations: Iterable[Relation]) -> str | None:
        """Convenience helper to delete multiple relationships.

        Returns the last non-null consistency token produced.
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
        """Return all relations matching the provided filters."""

    async def delete_user_relation(
        self,
        user: KeycloakUser,
        relation: RelationType,
        resource_type: Resource,
        resource_id: str,
    ) -> str | None:
        """Convenience helper to delete a relation for a user."""
        return await self.delete_relation(
            Relation(
                subject=RebacReference(Resource.USER, user.uid),
                relation=relation,
                resource=RebacReference(resource_type, resource_id),
            )
        )

    async def delete_user_relations(self, user: KeycloakUser) -> str | None:
        """Convenience helper to delete all relationships for a user."""
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
        """Return resource identifiers the subject can access for a permission."""

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
        """Return subjects related to the resource by a given relation."""

    async def lookup_user_resources(
        self,
        user: KeycloakUser,
        permission: RebacPermission,
        *,
        consistency_token: str | None = None,
    ) -> list[RebacReference] | RebacDisabledResult:
        """Convenience helper to lookup resources for a user."""
        group_relations, org_relations = await asyncio.gather(
            self.groups_list_to_relations(user),
            self.user_role_to_organization_relation(user),
        )

        return await self.lookup_resources(
            subject=RebacReference(Resource.USER, user.uid),
            permission=permission,
            resource_type=_resource_for_permission(permission),
            contextual_relations=group_relations | org_relations,
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
        """Evaluate whether a subject can perform an action on a resource."""

    async def check_permission_or_raise(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource: RebacReference,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> None:
        """Raise if the subject is not authorized to perform the action on the resource."""
        if not await self.has_permission(
            subject,
            permission,
            resource,
            contextual_relations=contextual_relations,
            consistency_token=consistency_token,
        ):
            raise AuthorizationError(
                subject.id, permission.value, resource.type, resource.id
            )

    async def check_user_permission_or_raise(
        self,
        user: KeycloakUser,
        permission: RebacPermission,
        resource_id: str,
        *,
        consistency_token: str | None = None,
    ) -> None:
        """Convenience helper to check permission for a user, raising if unauthorized."""
        group_relations, org_relations = await asyncio.gather(
            self.groups_list_to_relations(user),
            self.user_role_to_organization_relation(user),
        )

        resource_type = _resource_for_permission(permission)
        await self.check_permission_or_raise(
            RebacReference(Resource.USER, user.uid),
            permission,
            RebacReference(resource_type, resource_id),
            contextual_relations=group_relations | org_relations,
            consistency_token=consistency_token,
        )

    async def groups_list_to_relations(self, user: KeycloakUser) -> set[Relation]:
        """Helper to convert user groups to relations."""
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
        """Helper to convert user role to organization relation.

        Creates a relation between the user and the singleton 'fred' organization
        based on the user's Keycloak role (admin, editor, or viewer).
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
