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

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from fred_core.models import Base
from fred_core.teams.space_models import SpaceRow


class UserRow(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_lower_username", text("lower(username)")),
        CheckConstraint(
            "organization_kind = 'organization'", name="ck_users_organization_kind"
        ),
        ForeignKeyConstraint(
            ["organization_id", "organization_kind"],
            [SpaceRow.id, SpaceRow.kind],
            name="fk_users_organization",
            use_alter=True,
        ),
        {"extend_existing": True},
    )

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    # NULL identifies a newcomer awaiting admission, not an implicit organization.
    organization_id: Mapped[str | None] = mapped_column(String, index=True)
    organization_kind: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="organization"
    )
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    first_name: Mapped[str | None] = mapped_column(String, nullable=True)
    last_name: Mapped[str | None] = mapped_column(String, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    gcuVersionAccepted: Mapped[str | None] = mapped_column(Text(), nullable=True)
    gcuAcceptedAt: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_resources_storage_size: Mapped[int | None] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    avatar_object_storage_key: Mapped[str | None] = mapped_column(String, nullable=True)
