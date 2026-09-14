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

"""Typed application authorization helpers using raw application ids.

Both readers below take the engine's higher-consistency path: a revoked grant
has to deny on the next read, which an eventually-consistent read cannot
guarantee.
"""

from __future__ import annotations

from fred_core.common.team_id import is_personal_team_ref
from fred_core.security.models import Resource
from fred_core.security.rebac.rebac_engine import (
    AppPermission,
    RebacDisabledResult,
    RebacEngine,
    RebacReference,
    team_subject_and_context,
)

APPLICATION_CATALOG_NAMESPACE_PREFIX = "app__"

# Retain the catalog compatibility alias without prefixing authorization objects.
APPLICATION_CAPABILITY_NAMESPACE_PREFIX = APPLICATION_CATALOG_NAMESPACE_PREFIX

__all__ = [
    "APPLICATION_CAPABILITY_NAMESPACE_PREFIX",
    "APPLICATION_CATALOG_NAMESPACE_PREFIX",
    "app_ref",
    "application_catalog_id",
    "application_id_from_catalog_id",
    "can_team_use_application",
    "usable_application_ids",
]


def application_catalog_id(app_id: str) -> str:
    """Return the collision-free id used by the shared administration catalog."""

    return f"{APPLICATION_CATALOG_NAMESPACE_PREFIX}{app_id}"


def application_id_from_catalog_id(catalog_id: str) -> str:
    """Recover a raw application id from an exact application catalog id."""

    if not catalog_id.startswith(APPLICATION_CATALOG_NAMESPACE_PREFIX):
        raise ValueError(f"Not an application catalog id: {catalog_id!r}")
    app_id = catalog_id[len(APPLICATION_CATALOG_NAMESPACE_PREFIX) :]
    if not app_id:
        raise ValueError("Application catalog id must include an application id")
    return app_id


def app_ref(app_id: str) -> RebacReference:
    """Return the typed authorization reference for one raw application id."""

    return RebacReference(type=Resource.APP, id=app_id)


async def usable_application_ids(rebac: RebacEngine, team_id: str) -> set[str] | None:
    """Return raw ids of applications usable by one collaborative team.

    ``None`` retains the established disabled-ReBAC signal. Personal spaces
    always receive an empty set because applications are collaborative-only.
    """

    if is_personal_team_ref(team_id):
        return set()
    team_ref, context = team_subject_and_context(team_id)
    refs = await rebac.lookup_resources(
        team_ref,
        AppPermission.CAN_USE,
        Resource.APP,
        contextual_relations=context,
        consistency_token=RebacEngine.HIGHER_CONSISTENCY,
    )
    if isinstance(refs, RebacDisabledResult):
        return None
    return {ref.id for ref in refs}


async def can_team_use_application(
    rebac: RebacEngine, team_id: str, *, app_id: str
) -> bool:
    """Check whether a collaborative team may use one raw application id."""

    if is_personal_team_ref(team_id):
        return False
    team_ref, context = team_subject_and_context(team_id)
    return await rebac.has_permission(
        team_ref,
        AppPermission.CAN_USE,
        app_ref(app_id),
        contextual_relations=context,
        consistency_token=RebacEngine.HIGHER_CONSISTENCY,
    )
