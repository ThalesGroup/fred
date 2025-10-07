from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from fred_core.security.models import Action, Resource


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


@dataclass(frozen=True)
class Relation:
    """Edge connecting a subject (holder) to a resource (target)."""

    subject: RebacReference
    relation: RelationType
    resource: RebacReference


class RebacEngine(ABC):
    """Abstract base for relationship-based authorization providers."""

    @abstractmethod
    def add_relation(self, relation: Relation) -> str | None:
        """Persist a relationship edge into the underlying store.

        Returns a backend-specific consistency token when available.
        """

    def add_relations(self, relations: Iterable[Relation]) -> str | None:
        """Convenience helper to persist multiple relationships.

        Returns the last non-null consistency token produced.
        """

        token: str | None = None
        for relation in relations:
            token = self.add_relation(relation)
        return token

    @abstractmethod
    def lookup_resources(
        self,
        *,
        subject: RebacReference,
        permission: Action,
        resource_type: Resource,
        consistency_token: str | None = None,
    ) -> list[RebacReference]:
        """Return resource identifiers the subject can access for a permission."""

    @abstractmethod
    def has_permission(
        self,
        subject: RebacReference,
        permission: Action,
        resource: RebacReference,
        *,
        consistency_token: str | None = None,
    ) -> bool:
        """Evaluate whether a subject can perform an action on a resource."""
