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

from sqlalchemy import CheckConstraint, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base, utcnow

# The one and only row id. A single-row table is expressed the same way
# `platform_model_binding` expresses "chat only": a CHECK constraint at the
# database boundary, so the store cannot grow a second row even by mistake.
PLATFORM_PROMPT_SINGLETON_ID = "default"


class PlatformPromptRow(Base):
    """ORM model for the ``platform_prompt`` table (platform-wide platform prompt).

    The platform prompt is the FIRST block of every composed system prompt
    (`fred_runtime.react.react_prompting.compose_system_prompt`), ahead of
    any agent's own template. One row, platform-wide: teams
    already express their own intent through their agents'
    `system_prompt_template`, so V1 has no team dimension.

    Deliberately NOT a ReBAC relation, same reasoning as
    `platform_model_binding` (`platform_model_binding_models.py:44-55`): this
    is a platform-wide assertion with no subject and no team dimension, set by
    the org-admin authority. Read access is not a permission surface either —
    every agent turn on the deployment already renders this text.

    **An absent row means "no admin has ever saved one"**, and the runtime then
    falls back to the `platform_prompt` field of its shipped
    `config/platform_prompt.json`. That is distinct
    from a stored empty string, which is an admin deliberately suppressing the
    block — `build_platform_prompt_prefix` honours the difference, so clearing
    the field in the admin UI must write `""`, never delete the row.
    """

    __tablename__ = "platform_prompt"
    __table_args__ = (
        CheckConstraint(
            f"id = '{PLATFORM_PROMPT_SINGLETON_ID}'",
            name="ck_platform_prompt_singleton",
        ),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=PLATFORM_PROMPT_SINGLETON_ID
    )
    # Free text authored by a platform admin. Rendered verbatim into every
    # agent's system prompt, so it is trusted-by-construction: only a platform
    # admin can write it, and it must never be populated from a client-
    # forwarded field.
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
