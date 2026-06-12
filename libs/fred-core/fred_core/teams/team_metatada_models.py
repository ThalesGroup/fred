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

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from fred_core.models import Base


def utcnow() -> datetime:
    """Return timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class TeamMetadataRow(Base):
    """ORM model for the ``teammetadata`` table."""

    __tablename__ = "teammetadata"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(String(180), nullable=True)
    is_private: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    banner_object_storage_key: Mapped[str | None] = mapped_column(
        String(300), nullable=True
    )
    max_resources_storage_size: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    current_resources_storage_size: Mapped[int | None] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
