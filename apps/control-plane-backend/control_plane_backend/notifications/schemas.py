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
from typing import Annotated, ClassVar, Literal, Union

from fred_core.security.rebac.rebac_engine import TeamPermission
from pydantic import BaseModel, ConfigDict, Field

#: Most notifications one page returns.
MAX_PAGE_SIZE = 50


class NotificationType(str, Enum):
    AGENT_REPUBLISH_NEEDED = "agent.republish_needed"
    AGENT_MARKETPLACE_REMOVED = "agent.marketplace_removed"
    TEAM_JOIN_REQUESTED = "team.join_requested"
    TEAM_JOIN_REQUEST_ANSWERED = "team.join_request_answered"


class NotificationPayload(BaseModel):
    """Base of one payload class per type, which also declares the type's rules."""

    model_config = ConfigDict(extra="forbid")

    TYPE: ClassVar[NotificationType]
    #: The team right needed to receive and act on the type, checked at send
    #: time; losing it deletes the open ones. `None`: unfiltered.
    PERMISSION: ClassVar[TeamPermission | None] = None
    #: Asks the recipient to decide: an open one has no close button and survives
    #: "Clear all" until someone decides.
    DECISION: ClassVar[bool] = False


class AgentRepublishNeededPayload(NotificationPayload):
    """Another editor changed an agent the recipient published."""

    TYPE = NotificationType.AGENT_REPUBLISH_NEEDED
    PERMISSION = TeamPermission.CAN_UPDATE_AGENTS

    team_id: str
    team_name: str | None = None
    agent_instance_id: str
    agent_name: str
    entry_id: str
    editor_name: str


class AgentMarketplaceRemovedPayload(NotificationPayload):
    """An agent the recipient published left the marketplace without them."""

    TYPE = NotificationType.AGENT_MARKETPLACE_REMOVED
    PERMISSION = TeamPermission.CAN_UPDATE_AGENTS

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


class TeamJoinRequestedPayload(NotificationPayload):
    """A non-member asks to join a team the recipient administers."""

    TYPE = NotificationType.TEAM_JOIN_REQUESTED
    PERMISSION = TeamPermission.CAN_ADMINISTER_MEMBERS
    DECISION = True

    team_id: str
    team_name: str
    request_id: str
    requester_id: str
    requester_name: str
    message: str | None = None


class TeamJoinRequestAnsweredPayload(NotificationPayload):
    """An admin decided on the recipient's request; never names the admin."""

    TYPE = NotificationType.TEAM_JOIN_REQUEST_ANSWERED

    team_id: str
    team_name: str
    outcome: Literal["accepted", "refused"]


def group_key(type_: NotificationType, subject_id: str) -> str:
    """The key shared by every row about one subject, namespaced by type."""
    return f"{type_.value}:{subject_id}"


class _NotificationBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    team_id: str | None = None
    created_at: datetime
    expires_at: datetime
    seen_at: datetime | None = None
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


class TeamJoinRequestedNotification(_NotificationBase):
    type: Literal["team.join_requested"]
    payload: TeamJoinRequestedPayload


class TeamJoinRequestAnsweredNotification(_NotificationBase):
    type: Literal["team.join_request_answered"]
    payload: TeamJoinRequestAnsweredPayload


NotificationView = Annotated[
    Union[
        AgentRepublishNeededNotification,
        AgentMarketplaceRemovedNotification,
        TeamJoinRequestedNotification,
        TeamJoinRequestAnsweredNotification,
    ],
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


class NotificationTypeSetting(BaseModel):
    """One notification type and whether the platform sends it. The frontend
    names and describes it from `type`."""

    model_config = ConfigDict(extra="forbid")

    type: NotificationType
    enabled: bool
    disabled_by: str | None = None
    disabled_at: datetime | None = None


class NotificationTypeSettings(BaseModel):
    """Every type this version knows, in declaration order."""

    model_config = ConfigDict(extra="forbid")

    items: list[NotificationTypeSetting]


class SetNotificationTypeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        description="False hides every notification of the type from everyone, "
        "those already sent included; true shows every one still there."
    )
