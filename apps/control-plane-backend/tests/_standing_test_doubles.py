"""Account-standing test double shared by the startup and delete-route tests.

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
EVERYONE_ACTIVE = Relation(
    subject=RebacReference(Resource.USER, "*"),
    relation=RelationType.ACTIVE,
    resource=FRED,
)
STANDING_READY = Relation(
    subject=FRED, relation=RelationType.STANDING_READY, resource=FRED
)
_STANDING = {RelationType.ACTIVE, RelationType.STANDING_READY, RelationType.SUSPENDED}


def ban(person_id: str) -> Relation:
    return Relation(
        subject=RebacReference(Resource.USER, person_id),
        relation=RelationType.SUSPENDED,
        resource=FRED,
    )


class StandingRebacEngine(NoopRebacEngine):
    """Standing as the shipped model defines it: `active: [user:*] but not suspended`.

    Lifecycle writes land as stored tuples, and the base engine's own
    `require_user_standing` and `has_permission` read them back through
    `_has_permission_raw`. Every other permission is granted. Reference cleanup
    keeps standing tuples on the organization, as the OpenFGA engine does.
    """

    def __init__(
        self,
        *,
        enforces_standing: bool = True,
        relations: Iterable[Relation] = (),
        calls: list[str] | None = None,
    ) -> None:
        self._enforces_standing = enforces_standing
        self.relations: set[Relation] = set(relations)
        self.calls: list[str] = calls if calls is not None else []

    @property
    def enabled(self) -> bool:
        return True

    @property
    def enforces_standing(self) -> bool:
        return self._enforces_standing

    def _write(self, call: str, relation: Relation) -> str:
        self.calls.append(call)
        self.relations.add(relation)
        return self.HIGHER_CONSISTENCY

    async def validate_standing_model(self) -> None:
        self.calls.append("validate_standing_model")

    async def grant_default_standing(self) -> str | None:
        return self._write("grant_default_standing", EVERYONE_ACTIVE)

    async def mark_standing_seed_ready(self) -> str | None:
        return self._write("mark_standing_seed_ready", STANDING_READY)

    async def is_standing_seed_ready(self) -> bool:
        self.calls.append("is_standing_seed_ready")
        return STANDING_READY in self.relations

    async def remove_user_standing(self, user_id: str) -> str | None:
        if user_id == "*" or "#" in user_id:
            # `suspended: [user]` admits neither `user:*` nor a `user:…#…` userset:
            # OpenFGA answers the write with a 400.
            self.calls.append("remove_user_standing")
            raise ValidationException(
                status=400, reason="Bad Request", operation_name="write"
            )
        return self._write("remove_user_standing", ban(user_id))

    async def delete_all_relations_of_reference(
        self, reference: RebacReference
    ) -> str | None:
        self.calls.append("delete_all_relations_of_reference")
        if reference.type == Resource.USER and (
            not reference.id or reference.id == "*" or "#" in reference.id
        ):
            # The OpenFGA engine refuses a reference naming no single person.
            raise ValueError("Relationship cleanup takes one person id")
        self.relations = {
            stored
            for stored in self.relations
            if reference not in (stored.subject, stored.resource)
            or (stored.resource == FRED and stored.relation in _STANDING)
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
        if permission == RelationType.ACTIVE and resource == FRED:
            return (
                EVERYONE_ACTIVE in self.relations
                and ban(subject.id) not in self.relations
            )
        return True
