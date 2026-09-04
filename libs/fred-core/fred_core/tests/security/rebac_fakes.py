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

"""Shared `RebacEngine` stand-in for the capability authorization tests."""

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


class FakeRebacEngine(RebacEngine):
    """Minimal `RebacEngine` stand-in for the capability authorization paths.

    `lookup_resources` and `has_permission` record into separate slots so one
    instance can serve both a `ListObjects` and a `Check` assertion, and
    `checked_contextual_relations` grows in lockstep with `checked` so a
    multi-check path can be asserted call by call. Pass `denied_permissions`
    to answer some permissions differently from `permitted` — the only way to
    express "a team member whose team holds no grant". `disabled` drives
    `enabled`, so the engine's personal-team self-heal is skipped exactly as
    it is for a real disabled engine. Every other abstract method is a stub.
    """

    def __init__(
        self,
        *,
        resource_ids: list[str] | None = None,
        disabled: bool = False,
        permitted: bool = True,
        denied_permissions: set[RebacPermission] | None = None,
    ) -> None:
        self._resource_ids = resource_ids or []
        self._disabled = disabled
        self._permitted = permitted
        self._denied_permissions = denied_permissions or set()
        self.received_subject: RebacReference | None = None
        self.received_permission: RebacPermission | None = None
        self.received_resource_type: Resource | None = None
        self.received_contextual_relations: list[Relation] = []
        self.checked: list[tuple[RebacReference, RebacPermission, RebacReference]] = []
        self.checked_contextual_relations: list[list[Relation]] = []

    @property
    def enabled(self) -> bool:
        return not self._disabled

    async def _persist_relation(self, relation: Relation) -> str | None:
        return None

    async def delete_relation(self, relation: Relation) -> str | None:
        return None

    async def delete_all_relations_of_reference(
        self, reference: RebacReference
    ) -> str | None:
        return None

    async def delete_all_relations_of_type(self, resource_type: Resource) -> int:
        return 0

    async def list_relations(
        self,
        *,
        resource_type: Resource,
        relation: RelationType,
        subject: RebacReference,
        consistency_token: str | None = None,
    ) -> list[Relation]:
        return []

    async def lookup_resources(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource_type: Resource,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> list[RebacReference] | RebacDisabledResult:
        self.received_subject = subject
        self.received_permission = permission
        self.received_resource_type = resource_type
        self.received_contextual_relations = list(contextual_relations or [])
        if self._disabled:
            return RebacDisabledResult()
        return [
            RebacReference(type=resource_type, id=rid) for rid in self._resource_ids
        ]

    async def lookup_subjects(
        self,
        resource: RebacReference,
        relation: RelationType,
        subject_type: Resource,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> list[RebacReference]:
        return []

    async def has_permission(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource: RebacReference,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> bool:
        self.checked.append((subject, permission, resource))
        self.checked_contextual_relations.append(list(contextual_relations or []))
        if permission in self._denied_permissions:
            return False
        return self._permitted
