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

"""OpenFGA-backed implementation of the relationship authorization engine."""

from __future__ import annotations

from typing import Iterable

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

    async def delete_all_relations_of_reference(
        self, reference: RebacReference
    ) -> str | None:
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
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> list[RebacReference] | RebacDisabledResult:
        return RebacDisabledResult()

    async def lookup_subjects(
        self,
        resource: RebacReference,
        relation: RelationType,
        subject_type: Resource,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> list[RebacReference] | RebacDisabledResult:
        return RebacDisabledResult()

    async def has_direct_relation(
        self,
        subject: RebacReference,
        relation: RelationType,
        resource: RebacReference,
        *,
        consistency_token: str | None = None,
    ) -> bool:
        # Nothing is ever persisted under the no-op engine.
        return False

    async def has_permission(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource: RebacReference,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> bool:
        return True
