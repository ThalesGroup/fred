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

"""What the marketplace tells an entry's publisher. Called after the change
is committed; every function is best effort and never raises."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

from fred_core import KeycloakUser

from control_plane_backend.agent_marketplace.store import (
    AgentMarketplaceStore,
    EntryState,
    RemovalReason,
    RemovedEntry,
)
from control_plane_backend.notifications.schemas import (
    AgentMarketplaceRemovedPayload,
    AgentRepublishNeededPayload,
    NotificationType,
    group_key,
)
from control_plane_backend.notifications.service import (
    NotificationService,
    display_name,
)
from control_plane_backend.notifications.store import NotificationDraft

if TYPE_CHECKING:
    # The agent store imports this module: a runtime import would cycle.
    from control_plane_backend.agent_instances.store import AgentInstanceRecord

logger = logging.getLogger(__name__)

# The entry goes with its agent or team: there is nothing left to open.
_SILENT_REMOVALS = {RemovalReason.DELETED, RemovalReason.TEAM_DELETED}


def republish_group(entry_id: str) -> str:
    return group_key(NotificationType.AGENT_REPUBLISH_NEEDED, entry_id)


def _removed_group(entry: RemovedEntry) -> str:
    stamp = entry.removed_at.isoformat() if entry.removed_at else ""
    return group_key(
        NotificationType.AGENT_MARKETPLACE_REMOVED, f"{entry.entry_id}:{stamp}"
    )


async def notify_republish_needed(
    notifications: NotificationService | None,
    *,
    store: AgentMarketplaceStore,
    before: AgentInstanceRecord,
    after: AgentInstanceRecord,
    editor: KeycloakUser,
) -> None:
    """Ask the publisher to republish when another editor changed the agent."""
    if notifications is None or after.updated_at == before.updated_at:
        return
    try:
        entry = await store.get_for_agent(after.agent_instance_id, after.team_id)
        if (
            entry is None
            or entry.state != EntryState.PUBLISHED
            or entry.published_by in (None, editor.uid)
            or entry.snapshot_source_updated_at == after.updated_at
        ):
            return
        team_name = await store.team_name(entry.team_id)
    except Exception:
        logger.warning(
            "Failed to read the marketplace entry agent_instance_id=%s",
            after.agent_instance_id,
            exc_info=True,
        )
        return
    assert entry.published_by is not None
    await notifications.notify(
        [
            NotificationDraft(
                recipient_id=entry.published_by,
                group_key=republish_group(entry.entry_id),
                team_id=str(entry.team_id),
                payload=AgentRepublishNeededPayload(
                    team_id=str(entry.team_id),
                    team_name=team_name,
                    agent_instance_id=entry.agent_instance_id,
                    agent_name=after.display_name,
                    entry_id=entry.entry_id,
                    editor_name=display_name(editor),
                ),
            )
        ]
    )


async def resolve_republished(
    notifications: NotificationService | None, *, entry_id: str, user: KeycloakUser
) -> None:
    if notifications is not None:
        await notifications.resolve(
            [republish_group(entry_id)],
            actor_uid=user.uid,
            actor_name=display_name(user),
            outcome="republished",
        )


async def notify_unpublished(
    notifications: NotificationService | None,
    removed: Sequence[RemovedEntry],
    *,
    actor_uid: str | None,
    actor_name: str | None = None,
) -> None:
    """Resolve the entries' republish requests and tell each publisher who did
    not cause it that their agent entered the Removed state, in one insert."""
    if notifications is None or not removed:
        return
    await notifications.resolve(
        [republish_group(entry.entry_id) for entry in removed],
        actor_uid=actor_uid,
        actor_name=actor_name,
        outcome="removed",
    )
    drafts = [
        NotificationDraft(
            recipient_id=entry.published_by,
            group_key=_removed_group(entry),
            team_id=str(entry.team_id),
            payload=AgentMarketplaceRemovedPayload(
                team_id=str(entry.team_id),
                team_name=entry.team_name,
                agent_instance_id=entry.agent_instance_id,
                agent_name=entry.display_name,
                entry_id=entry.entry_id,
                reason=entry.reason.value,
                message=entry.message,
            ),
        )
        for entry in removed
        if entry.state == EntryState.REMOVED
        and entry.reason not in _SILENT_REMOVALS
        and entry.published_by is not None
        and entry.published_by != actor_uid
    ]
    await notifications.notify(drafts)
