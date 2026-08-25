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

# V1 supports only the `chat` capability — `language`/`embedding`/`image`
# have no production consumer yet. Kept as a plain
# constant (not the global `fred_sdk.contracts.context.ModelCapability`
# enum) to avoid an ORM-layer dependency on that contract module purely for
# one literal string; the CHECK constraint below is what actually enforces
# it at the database boundary.
CHAT_MODEL_CAPABILITY = "chat"


class PlatformModelBindingRow(Base):
    """ORM model for the ``platform_model_binding`` table (platform-wide model
    routing override, `fred_sdk.contracts.context.ModelBinding`).

    Chat-only in V1: at most one row ever exists, always keyed
    `model_capability="chat"` — enforced by the CHECK
    constraint below, not just application code, so the normal store/service
    path structurally cannot insert a `language`/`embedding`/`image` row.
    The row asserts the concrete `(provider, name, settings)` the platform
    operator has decided is authoritative for `chat`, overriding whatever
    every pod would otherwise resolve locally.

    Deliberately NOT a ReBAC relation, same reasoning as `model_reasoning`
    (`model_reasoning_models.py:33-42`): this is a platform-wide routing
    assertion, not a per-team permission — it has no subject, no team
    dimension. That is also why the runtime bypasses the `usable_model_ids`
    ReBAC gate for a platform-bound selection (`fred-runtime`'s
    `RoutedChatModelFactory.build_for_chat`): a platform
    binding is set by the same org-admin authority that could otherwise just
    grant `can_use` for every team anyway, not a new authorization surface
    being bypassed.

    **An absent row means unset** — there is no natural "off" value for a
    `(provider, name)` pair the way `reasoning_enabled=False` works for
    `model_reasoning`, so "clear this binding" is row deletion, not a stored
    false.
    """

    __tablename__ = "platform_model_binding"
    __table_args__ = (
        CheckConstraint(
            f"model_capability = '{CHAT_MODEL_CAPABILITY}'",
            name="ck_platform_model_binding_chat_only",
        ),
    )

    model_capability: Mapped[str] = mapped_column(
        String, primary_key=True, default=CHAT_MODEL_CAPABILITY
    )
    provider: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # JSON-encoded `ModelBinding.settings` (`ModelBindingSettings.model_dump
    # (mode="json", exclude_none=True)`). `ModelBindingSettings` has no
    # credential-designated field and no generic auth/header/cookie/client
    # passthrough container, and `extra="forbid"` rejects any key outside
    # its named allowlist before a row ever reaches this column — it does
    # not inspect whether an arbitrary value in an allowed field is itself a
    # secret; operators must never place one there. `store.py`'s
    # `_binding_row_to_record` re-validates through `ModelBinding` on every
    # read, so a row that bypassed this column's own writer still fails
    # closed at lookup.
    settings_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
