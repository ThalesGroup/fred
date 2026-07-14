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

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base

# Fixed primary key value: this table only ever holds zero or one row. There
# is no per-tenant/per-org dimension to key on (single-organization model,
# `ORGANIZATION_ID` = "fred" everywhere else in the schema).
SINGLETON_ID = "platform"


class PlatformBootstrapRow(Base):
    """ORM model for the ``platformbootstrap`` singleton row.

    AUTHZ-07 (RFC FRED-AUTHORIZATION-TARGET-MODEL-RFC.md Part 8, §42.3): the
    durable "root bootstrap has completed" marker. Deliberately not derived
    from live OpenFGA state (`lookup_subjects` on `platform_admin`) — removing
    every `platform_admin` later must not silently reopen root bootstrap for
    anyone who still holds the deploy-time secret. The row either exists
    (bootstrap is permanently done) or it does not (bootstrap has never run).
    """

    __tablename__ = "platformbootstrap"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=SINGLETON_ID)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_by: Mapped[str] = mapped_column(String, nullable=False)
