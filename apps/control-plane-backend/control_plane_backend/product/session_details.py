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

from urllib.parse import quote

from fred_core.common import TeamId

from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.product.schemas import SessionDetails


async def get_session(
    *,
    team_id: TeamId,
    session_id: str,
    user_id: str,
    deps: ProductServiceDependencies,
) -> SessionDetails | None:
    """Read an owned session and its history route without preparing execution.

    Call after team authorization; unknown and foreign sessions return None.
    """
    record = await deps.get_session_metadata_store().get(session_id)
    if (
        record is None
        or str(record.team_id) != str(team_id)
        or record.user_id != user_id
    ):
        return None

    instance = (
        await deps.get_agent_instance_store().get_for_team(
            record.agent_instance_id, team_id
        )
        if record.agent_instance_id is not None
        else None
    )
    details = SessionDetails.model_validate(record, from_attributes=True)
    details.agent_deleted = record.agent_instance_id is not None and instance is None
    # The captured runtime survives agent deletion; a live binding only fills
    # the gap for sessions created before runtime snapshots were recorded.
    runtime_id = record.source_runtime_id or (
        instance.source_runtime_id if instance is not None else None
    )
    source = next(
        (
            item
            for item in deps.configuration.platform.runtime_catalog_sources
            if item.runtime_id == runtime_id and item.enabled
        ),
        None,
    )
    if source is not None and source.ingress_prefix:
        prefix = source.ingress_prefix.rstrip("/")
        details.messages_url = (
            f"{prefix}/agents/sessions/{quote(session_id, safe='')}/messages"
        )
    return details
