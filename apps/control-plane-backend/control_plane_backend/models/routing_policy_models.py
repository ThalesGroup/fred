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

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base, utcnow


class TeamRoutingPolicyRow(Base):
    """ORM model for the ``team_routing_policy`` table (TEAM-05, #2118,
    `TEAM-ROUTING-POLICY-RFC.md` §3/§10).

    One row per team (including personal teams, which use this table exactly
    like any other team — see the RFC's §1 "not a special case"). Full
    replacement on every write (`PATCH` in the RFC is a full typed
    replacement, no per-field patch semantics) — mirrors
    ``team_capability_settings``'s select-then-write upsert shape.
    """

    __tablename__ = "team_routing_policy"

    team_id: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    chat_default_profile_id: Mapped[str | None] = mapped_column(String, nullable=True)
    agent_profile_overrides_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
        comment="JSON-serialized {agent_id: target_profile_id} dict.",
    )
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
