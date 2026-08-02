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

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base, utcnow


class ModelReasoningRow(Base):
    """ORM model for the ``model_reasoning`` table (REASON-01,
    `MODEL-REASONING-ENABLEMENT-RFC.md` §5.5 option A).

    One row per ``kind="model"`` capability id — the platform admin's global
    reasoning activation for that model. Deliberately NOT a ReBAC relation
    (§5.1): this is an activation ("does this model run with reasoning"), not
    a permission — it has no subject, no team dimension, so building it as a
    grant would mean duplicating the capability type's whole enablement
    lattice for an axis with no per-subject semantics at all. Per-team model
    *authorization* stays exactly where it is, on ReBAC ``can_use``.

    **An absent row means OFF** (§5.6). Enabling a model and enabling its
    reasoning are two separate admin actions, in that order; the second is
    never implied by the first. Consequence, deliberate and documented in the
    release notes: a deployment that ran reasoning through ``models_catalog.yaml``
    alone stops reasoning on upgrade until an administrator switches it on
    (§5.6.1).
    """

    __tablename__ = "model_reasoning"

    model_capability_id: Mapped[str] = mapped_column(String, primary_key=True)
    reasoning_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment=(
            "Whether this model's thinking-capable profiles may run with "
            "reasoning on. Absent row = off (REASON-01 §5.6)."
        ),
    )
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
