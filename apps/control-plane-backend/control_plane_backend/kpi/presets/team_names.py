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

"""Team-id to display-name resolution, shared by the presets that label a team.

Its own module rather than `kpi/utils.py`: that one is a stdlib-only leaf every
preset imports for `resolve_interval`, and the container this needs drags in
keycloak and sqlalchemy.
"""

from __future__ import annotations

import logging

from fastapi import Request
from fred_core.common import TeamId

from control_plane_backend.app.dependencies import get_application_container

logger = logging.getLogger(__name__)


async def resolve_team_names(request: Request, team_ids: list[str]) -> dict[str, str]:
    """Return {team_id: display_name}, falling back to the id on any error.

    A team's name lives in `team_metadata_store`, not in Keycloak (AUTHZ-05
    review item 9).
    """
    if not team_ids:
        return {}
    try:
        store = get_application_container(request).get_team_metadata_store()
        metadata_by_id = await store.get_by_team_ids([TeamId(tid) for tid in team_ids])
        return {
            tid: metadata_by_id[TeamId(tid)].name
            if TeamId(tid) in metadata_by_id
            else tid
            for tid in team_ids
        }
    except Exception:
        # Logged, not silent: an unreachable store and a genuinely deleted team
        # both render as raw ids, and only this line tells the two apart.
        logger.warning("Falling back to raw team ids for KPI labels", exc_info=True)
        return {tid: tid for tid in team_ids}
