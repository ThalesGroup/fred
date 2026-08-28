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

"""Team-authorized Fred application discovery."""

from __future__ import annotations

from fred_core import KeycloakUser, TeamPermission
from fred_core.common import TeamId, is_personal_team_id

from control_plane_backend.applications.catalog import (
    GENERATED_APPLICATION_CATALOG_SOURCE,
    ApplicationCatalogSource,
)
from control_plane_backend.applications.schemas import ApplicationList
from control_plane_backend.capabilities.authz import usable_capability_ids
from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.teams.schemas import TeamNotFoundError
from control_plane_backend.teams.system import resolve_system_team_id


async def list_team_applications(
    *,
    user: KeycloakUser,
    team_id: TeamId,
    deps: ProductServiceDependencies,
    catalog_source: ApplicationCatalogSource = GENERATED_APPLICATION_CATALOG_SOURCE,
) -> ApplicationList:
    """Return installed applications admitted for one collaborative team.

    Authorization intentionally precedes both team-registry and application
    metadata reads. A public non-member (or a platform administrator who is
    not a member) therefore receives 403 without learning whether the team or
    an application exists.
    """

    canonical_team_id = resolve_system_team_id(user, team_id) or team_id
    rebac = deps.team_dependencies.rebac
    await rebac.check_user_team_permission_or_raise(
        user,
        TeamPermission.CAN_USE_TEAM_APPLICATIONS,
        str(canonical_team_id),
    )

    # Personal spaces are an explicit V1 ceiling even if capability default-on
    # would make their team subject pass ``capability#can_use``.
    if is_personal_team_id(str(canonical_team_id)):
        return catalog_source.load().empty_list()

    metadata = await deps.get_team_metadata_store().get_by_team_id(canonical_team_id)
    if metadata is None:
        raise TeamNotFoundError(canonical_team_id)

    catalog = catalog_source.load()
    usable_ids = await usable_capability_ids(rebac, canonical_team_id)
    items = [
        item.summary()
        for item in catalog.items
        if usable_ids is None or item.capability_id in usable_ids
    ]
    return ApplicationList(
        schema_version="1",
        catalog_revision=catalog.catalog_revision,
        items=items,
    )
