from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from fred_core.security.models import AuthorizationError, Resource
from fred_core.security.structure import KeycloakUser


@dataclass(frozen=True)
class RebacReference:
    """Identifies a subject or resource within the authorization graph."""

    type: Resource
    id: str


class RelationType(str, Enum):
    """Relationship labels encoded in the graph."""

    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"
    PARENT = "parent"
    MEMBER = "member"


class TagPermission(str, Enum):
    """Tag permissions encoded in the graph."""

    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    SHARE = "share"


class DocumentPermission(str, Enum):
    """Document permissions encoded in the graph."""

    READ = "read"
    UPDATE = "update"
    DELETE = "delete"


RebacPermission = TagPermission | DocumentPermission


def _resource_for_permission(permission: RebacPermission) -> Resource:
    if isinstance(permission, TagPermission):
        return Resource.TAGS
    if isinstance(permission, DocumentPermission):
        return Resource.DOCUMENTS
    raise ValueError(f"Unsupported permission type: {permission!r}")


@dataclass(frozen=True)
class Relation:
    """Edge connecting a subject (holder) to a resource (target)."""

    subject: RebacReference
    relation: RelationType
    resource: RebacReference


class RebacEngine(ABC):
    """Abstract base for relationship-based authorization providers."""

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
    async def delete_reference_relations(self, reference: RebacReference) -> str | None:
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
    ) -> list[Relation]:
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
        return await self.delete_reference_relations(
            RebacReference(Resource.USER, user.uid)
        )

    @abstractmethod
    async def lookup_resources(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource_type: Resource,
        *,
        consistency_token: str | None = None,
    ) -> list[RebacReference]:
        """Return resource identifiers the subject can access for a permission."""

    @abstractmethod
    async def lookup_subjects(
        self,
        resource: RebacReference,
        relation: RelationType,
        subject_type: Resource,
        *,
        consistency_token: str | None = None,
    ) -> list[RebacReference]:
        """Return subjects related to the resource by a given relation."""

    async def lookup_user_resources(
        self,
        user: KeycloakUser,
        permission: RebacPermission,
        *,
        consistency_token: str | None = None,
    ) -> list[RebacReference]:
        """Convenience helper to lookup resources for a user."""
        return await self.lookup_resources(
            subject=RebacReference(Resource.USER, user.uid),
            permission=permission,
            resource_type=_resource_for_permission(permission),
            consistency_token=consistency_token,
        )

    @abstractmethod
    async def has_permission(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource: RebacReference,
        *,
        consistency_token: str | None = None,
    ) -> bool:
        """Evaluate whether a subject can perform an action on a resource."""

    async def check_permission_or_raise(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource: RebacReference,
        *,
        consistency_token: str | None = None,
    ) -> None:
        """Raise if the subject is not authorized to perform the action on the resource."""
        if not self.has_permission(
            subject, permission, resource, consistency_token=consistency_token
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
        resource_type = _resource_for_permission(permission)
        await self.check_permission_or_raise(
            RebacReference(Resource.USER, user.uid),
            permission,
            RebacReference(resource_type, resource_id),
            consistency_token=consistency_token,
        )
