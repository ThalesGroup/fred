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
    def add_relation(self, relation: Relation) -> None:
        """Persist a relationship edge into the underlying store."""

    def add_relations(self, relations: Iterable[Relation]) -> None:
        """Convenience helper to persist multiple relationships."""

        for relation in relations:
            self.add_relation(relation)

    @abstractmethod
    def get_relations_as_subject(self, subject: RebacReference) -> list[Relation]:
        """Return all relations where the provided reference is the subject."""

    @abstractmethod
    def get_relations_as_resource(self, resource: RebacReference) -> list[Relation]:
        """Return all relations where the provided reference is the resource."""

    @abstractmethod
    def has_permission(
        self,
        subject: RebacReference,
        permission: Action,
        resource: RebacReference,
    ) -> bool:
        """Evaluate whether a subject can perform an action on a resource."""
