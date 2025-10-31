"""OpenFGA-backed implementation of the relationship authorization engine."""

from __future__ import annotations

from fred_core.security.models import Resource
from fred_core.security.rebac.rebac_engine import (
    RebacDisabledResult,
    RebacEngine,
    RebacPermission,
    RebacReference,
    Relation,
    RelationType,
)


class NoopRebacEngine(RebacEngine):
    """
    A no-op ReBAC engine that authorizes everything and does not persist anything.

    Return `RebacDisabledResult` for all lookup / list operations so that caller can handle this case.
    """

    @property
    def enabled(self) -> bool:
        return False

    async def add_relation(self, relation: Relation) -> str | None:
        return None

    async def delete_relation(self, relation: Relation) -> str | None:
        return None

    async def delete_reference_relations(self, reference: RebacReference) -> str | None:
        return None

    async def list_relations(
        self,
        *,
        resource_type: Resource,
        relation: RelationType,
        subject_type: Resource | None = None,
        consistency_token: str | None = None,
    ) -> list[Relation] | RebacDisabledResult:
        return RebacDisabledResult()

    async def lookup_resources(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource_type: Resource,
        *,
        consistency_token: str | None = None,
    ) -> list[RebacReference] | RebacDisabledResult:
        return RebacDisabledResult()

    async def lookup_subjects(
        self,
        resource: RebacReference,
        relation: RelationType,
        subject_type: Resource,
        *,
        consistency_token: str | None = None,
    ) -> list[RebacReference] | RebacDisabledResult:
        return RebacDisabledResult()

    async def has_permission(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource: RebacReference,
        *,
        consistency_token: str | None = None,
    ) -> bool:
        return True
