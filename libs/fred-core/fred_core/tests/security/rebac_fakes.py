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

"""Shared `RebacEngine` stand-ins for the authorization tests."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Iterable

from openfga_sdk.api_client import ApiClient
from openfga_sdk.configuration import Configuration

from fred_core.security.models import Resource
from fred_core.security.rebac.openfga_engine import OpenFgaRebacEngine
from fred_core.security.rebac.openfga_schema import DEFAULT_SCHEMA
from fred_core.security.rebac.rebac_engine import (
    RebacDisabledResult,
    RebacEngine,
    RebacPermission,
    RebacReference,
    Relation,
    RelationType,
)
from fred_core.security.structure import OpenFgaRebacConfig

_SUSPENDED_ON_PLATFORM = ("suspended", "platform:fred")


class AccountStatusStore:
    """An OpenFGA store holding suspensions, as the client sees it.

    The shipped model is served through the SDK's own parser. A Check of
    `suspended` on the platform is true only for a stored person, as
    `suspended: [user]` is; every other Check and BatchCheck item is allowed.
    ListObjects returns the `objects` stored for its (user, relation, type).
    Each call is recorded with its options.
    """

    def __init__(
        self,
        suspended: Iterable[str] = (),
        *,
        unavailable: bool = False,
        objects: dict[tuple[str, str, str], list[str]] | None = None,
    ) -> None:
        self.suspended = set(suspended)
        self.unavailable = unavailable
        self.objects = objects or {}
        self.checks: list[tuple[str, str, str, object]] = []
        self.batch_checks: list[tuple[list[tuple[str, str, str]], object]] = []
        self.list_objects_calls: list[tuple[str, str, str, object]] = []

    def account_status_checks(self) -> list[tuple[str, object]]:
        """(subject, consistency) of each Check asking about a suspension."""
        return [
            (user, consistency)
            for user, relation, obj, consistency in self.checks
            if (relation, obj) == _SUSPENDED_ON_PLATFORM
        ]

    async def read_latest_authorization_model(self):
        payload = {
            "authorization_model": {
                "id": "synthetic-latest",
                **json.loads(DEFAULT_SCHEMA),
            }
        }
        async with ApiClient(Configuration(api_url="http://openfga.invalid")) as api:
            return api.deserialize(
                SimpleNamespace(data=json.dumps(payload)),
                "ReadAuthorizationModelResponse",
            )

    async def check(self, body, options):
        self.checks.append(
            (body.user, body.relation, body.object, options.get("consistency"))
        )
        if self.unavailable:
            raise ConnectionError("synthetic upstream canary")
        if (body.relation, body.object) == _SUSPENDED_ON_PLATFORM:
            return SimpleNamespace(
                allowed=body.user in {f"user:{p}" for p in self.suspended}
            )
        return SimpleNamespace(allowed=True)

    async def batch_check(self, body, options):
        self.batch_checks.append(
            (
                [(item.user, item.relation, item.object) for item in body.checks],
                options.get("consistency"),
            )
        )
        return SimpleNamespace(
            result=[
                SimpleNamespace(
                    allowed=True, correlation_id=item.correlation_id, error=None
                )
                for item in body.checks
            ]
        )

    async def list_objects(self, body, options):
        self.list_objects_calls.append(
            (body.user, body.relation, body.type, options.get("consistency"))
        )
        return SimpleNamespace(
            objects=self.objects.get((body.user, body.relation, body.type), [])
        )


def account_status_engine(
    store: AccountStatusStore, *, requires_active_accounts: bool = True
) -> OpenFgaRebacEngine:
    """The engine a service builds with a delegation switch on, over `store`."""
    engine = OpenFgaRebacEngine(
        OpenFgaRebacConfig(api_url="http://openfga.invalid"),  # pyright: ignore[reportArgumentType]
        token="synthetic-token",  # nosec B106 - synthetic fixture
        requires_active_accounts=requires_active_accounts,
    )
    engine._cached_client = store  # pyright: ignore[reportAttributeAccessIssue]
    return engine


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
        self.received_permission: RebacPermission | RelationType | None = None
        self.received_resource_type: Resource | None = None
        self.received_contextual_relations: list[Relation] = []
        self.checked: list[
            tuple[RebacReference, RebacPermission | RelationType, RebacReference]
        ] = []
        self.checked_contextual_relations: list[list[Relation]] = []
        # Consistency is a correctness argument for app admission, so a test has
        # to be able to assert the value each read requested, not only that a
        # read happened. Both lists grow in lockstep with their call list.
        self.checked_consistency_tokens: list[str | None] = []
        self.lookup_resources_consistency_tokens: list[str | None] = []

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

    async def list_relations(
        self,
        *,
        resource_type: Resource,
        relation: RelationType,
        subject: RebacReference,
        consistency_token: str | None = None,
    ) -> list[Relation]:
        return []

    async def _lookup_resources_raw(
        self,
        subject: RebacReference,
        permission: RebacPermission | RelationType,
        resource_type: Resource,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> list[RebacReference] | RebacDisabledResult:
        self.received_subject = subject
        self.received_permission = permission
        self.received_resource_type = resource_type
        self.received_contextual_relations = list(contextual_relations or [])
        self.lookup_resources_consistency_tokens.append(consistency_token)
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

    async def _has_permission_raw(
        self,
        subject: RebacReference,
        permission: RebacPermission | RelationType,
        resource: RebacReference,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> bool:
        self.checked.append((subject, permission, resource))
        self.checked_contextual_relations.append(list(contextual_relations or []))
        self.checked_consistency_tokens.append(consistency_token)
        if permission in self._denied_permissions:
            return False
        return self._permitted
