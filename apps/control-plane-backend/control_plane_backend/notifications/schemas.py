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

"""Notification types, their payloads and the caller-facing views.

The frontend renders every text from `type` and `payload`; a payload carries
ids plus the display names as they were when the notification was created.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

#: Most notifications one page returns.
MAX_PAGE_SIZE = 50


class NotificationType(str, Enum):
    AGENT_REPUBLISH_NEEDED = "agent.republish_needed"
    AGENT_MARKETPLACE_REMOVED = "agent.marketplace_removed"


class _Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentRepublishNeededPayload(_Payload):
    """Another editor changed an agent the recipient published."""

    team_id: str
    team_name: str | None = None
    agent_instance_id: str
    agent_name: str
    entry_id: str
    editor_name: str


class AgentMarketplaceRemovedPayload(_Payload):
    """An agent the recipient published left the marketplace without them."""

    team_id: str
    team_name: str | None = None
    agent_instance_id: str
    agent_name: str
    entry_id: str
    reason: str = Field(
        description="The removal reason code, as `AgentMarketplaceState.removed_reason`."
    )
    message: str | None = Field(
        default=None, description="The platform admin's message, if any."
    )


PAYLOAD_MODELS: dict[NotificationType, type[_Payload]] = {
    NotificationType.AGENT_REPUBLISH_NEEDED: AgentRepublishNeededPayload,
    NotificationType.AGENT_MARKETPLACE_REMOVED: AgentMarketplaceRemovedPayload,
}


def validate_payload(type_: str, payload: BaseModel | dict[str, Any]) -> dict[str, Any]:
    """The payload as stored; raises on an unknown type or an invalid payload."""
    model = PAYLOAD_MODELS[NotificationType(type_)]
    data = payload.model_dump() if isinstance(payload, BaseModel) else payload
    return model.model_validate(data).model_dump(mode="json")


class _NotificationBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    team_id: str | None = None
    created_at: datetime
    expires_at: datetime
    seen_at: datetime | None = None
    read_at: datetime | None = Field(
        default=None, description="Null while the tile keeps its unread style."
    )
    handled_at: datetime | None = Field(
        default=None,
        description="Set once someone else acted on the subject; the tile then "
        "shows `handled_by_name` instead of its buttons.",
    )
    handled_by_name: str | None = None
    handled_outcome: str | None = None


class AgentRepublishNeededNotification(_NotificationBase):
    type: Literal["agent.republish_needed"]
    payload: AgentRepublishNeededPayload


class AgentMarketplaceRemovedNotification(_NotificationBase):
    type: Literal["agent.marketplace_removed"]
    payload: AgentMarketplaceRemovedPayload


NotificationView = Annotated[
    Union[AgentRepublishNeededNotification, AgentMarketplaceRemovedNotification],
    Field(discriminator="type"),
]


class NotificationPage(BaseModel):
    """One page of the caller's notifications, newest first."""

    model_config = ConfigDict(extra="forbid")

    items: list[NotificationView]
    next_cursor: str | None = Field(
        default=None,
        description="Opaque; pass it as `before` for the next page. Null on the last.",
    )


class NotificationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unseen_count: int


class MarkNotificationsSeenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    up_to: str = Field(
        description="The newest notification id the popover listed; it and every "
        "older notification are marked seen."
    )
