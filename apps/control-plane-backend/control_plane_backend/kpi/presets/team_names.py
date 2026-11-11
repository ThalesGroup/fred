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
from collections import Counter

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


def build_agent_labels(
    id_to_name: dict[str, str],
    id_to_team_id: dict[str, str],
    team_names: dict[str, str],
) -> dict[str, str]:
    """agent_instance_id -> the label its series is drawn under.

    Instance names are not unique across teams, so a cross-team chart qualifies
    each one with its owning team. Pass an empty `team_names` to keep bare
    names, which is what a team-scoped request does.
    """
    qualified: dict[str, str] = {}
    for instance_id, name in id_to_name.items():
        team_name = team_names.get(id_to_team_id.get(instance_id, ""))
        qualified[instance_id] = f"{name} - {team_name}" if team_name else name

    # Two instances can still land on one label. The id stays the accumulation
    # key throughout, so only the display label needs breaking apart.
    label_counts = Counter(qualified.values())
    return {
        instance_id: f"{label} ({instance_id[:8]})"
        if label_counts[label] > 1
        else label
        for instance_id, label in qualified.items()
    }
