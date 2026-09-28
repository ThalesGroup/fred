"""Account-status test double shared by the startup and delete-route tests.

Not named `test_*` so pytest never collects it as a test module.
"""

from __future__ import annotations

from typing import Iterable

from fred_core import (
    ORGANIZATION_ID,
    RebacPermission,
    RebacReference,
    Relation,
    RelationType,
    Resource,
)
from fred_core.security.rebac.noop_engine import NoopRebacEngine
from openfga_sdk.exceptions import ValidationException

FRED = RebacReference(Resource.ORGANIZATION, ORGANIZATION_ID)


def ban(person_id: str) -> Relation:
    return Relation(
        subject=RebacReference(Resource.USER, person_id),
        relation=RelationType.SUSPENDED,
        resource=FRED,
    )


class AccountStatusRebacEngine(NoopRebacEngine):
    """Account status as the shipped model defines it: `suspended: [user]`.

    A check of `suspended` on the organization is true only when that person's
    direct tuple is stored. Lifecycle writes land as stored tuples, and the base
    engine's own `require_active_account` reads them back through
    `_has_permission_raw`. Every other permission is granted. Reference
    cleanup keeps `suspended` tuples on the organization, as the OpenFGA engine does.
    """

    def __init__(
        self,
        *,
        requires_active_accounts: bool = True,
        relations: Iterable[Relation] = (),
        calls: list[str] | None = None,
    ) -> None:
        self._requires_active_accounts = requires_active_accounts
        self.relations: set[Relation] = set(relations)
        self.calls: list[str] = calls if calls is not None else []

    @property
    def enabled(self) -> bool:
        return True

    @property
    def requires_active_accounts(self) -> bool:
        return self._requires_active_accounts

    async def validate_account_status_model(self) -> None:
        self.calls.append("validate_account_status_model")

    async def suspend_account(self, user_id: str) -> str | None:
        self.calls.append("suspend_account")
        if user_id == "*" or "#" in user_id:
            # `suspended: [user]` admits neither `user:*` nor a `user:…#…` userset:
            # OpenFGA answers the write with a 400.
            raise ValidationException(
                status=400, reason="Bad Request", operation_name="write"
            )
        self.relations.add(ban(user_id))
        return self.HIGHER_CONSISTENCY

    async def delete_all_relations_of_reference(
        self, reference: RebacReference
    ) -> str | None:
        self.calls.append("delete_all_relations_of_reference")
        self.relations = {
            stored
            for stored in self.relations
            if reference not in (stored.subject, stored.resource)
            or (stored.resource == FRED and stored.relation == RelationType.SUSPENDED)
        }
        return self.HIGHER_CONSISTENCY

    async def _has_permission_raw(
        self,
        subject: RebacReference,
        permission: RebacPermission | RelationType,
        resource: RebacReference,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> bool:
        if permission == RelationType.SUSPENDED and resource == FRED:
            return (
                Relation(
                    subject=subject, relation=RelationType.SUSPENDED, resource=FRED
                )
                in self.relations
            )
        return True
