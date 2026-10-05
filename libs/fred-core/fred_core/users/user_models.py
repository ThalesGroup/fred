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

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    Index,
    String,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from fred_core.models import Base


class GcuVersionsType(enum.Enum):
    V1 = "v1"


class UserRow(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_lower_username", text("lower(username)")),
        {"extend_existing": True},
    )

    id: Mapped[Uuid] = mapped_column(Uuid, primary_key=True)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    first_name: Mapped[str | None] = mapped_column(String, nullable=True)
    last_name: Mapped[str | None] = mapped_column(String, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    admission_attribute: Mapped[str | list[str] | None] = mapped_column(
        JSON, nullable=True
    )
    admission_claim_path: Mapped[str | None] = mapped_column(String(64), nullable=True)
    admission_issued_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    admission_expires_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    admission_conflicted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    gcuVersionAccepted: Mapped[GcuVersionsType | None] = mapped_column(
        Enum(GcuVersionsType, name="gcu_version_type"), nullable=True
    )
    gcuAcceptedAt: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_resources_storage_size: Mapped[int | None] = mapped_column(
        BigInteger, nullable=False, default=0
    )
