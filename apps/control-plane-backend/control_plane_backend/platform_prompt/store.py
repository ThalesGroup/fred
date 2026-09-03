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

from dataclasses import dataclass
from datetime import datetime

from fred_core.sql import make_session_factory, use_session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.models.base import utcnow
from control_plane_backend.models.platform_prompt_models import (
    PLATFORM_PROMPT_SINGLETON_ID,
    PlatformPromptRow,
)


@dataclass(frozen=True)
class StoredPlatformPrompt:
    """The stored platform-prompt row."""

    text: str
    updated_by: str | None
    updated_at: datetime | None


class PlatformPromptStore:
    """Pure CRUD over ``platform_prompt`` — at most one row, always keyed
    `id="default"` (CHECK-enforced).

    Same select-then-write upsert shape and the same separation of concerns as
    `PlatformModelBindingStore`: this store never checks authorization, that is
    `platform_prompt/service.py`'s job.

    There is deliberately no `delete`: unlike a `(provider, name)` binding, a
    text field HAS a natural "off" value, and the empty string is it. Row
    absence therefore keeps a single, unambiguous meaning — "no admin has ever
    saved one, use the pod default" — which a delete would otherwise collide
    with.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def get(
        self, *, session: AsyncSession | None = None
    ) -> StoredPlatformPrompt | None:
        async with use_session(self._sessions, session) as s:
            row = (
                await s.execute(
                    select(PlatformPromptRow).where(
                        PlatformPromptRow.id == PLATFORM_PROMPT_SINGLETON_ID
                    )
                )
            ).scalar_one_or_none()
        if row is None:
            return None
        return StoredPlatformPrompt(
            text=row.text,
            updated_by=row.updated_by,
            updated_at=row.updated_at,
        )

    async def set(
        self,
        *,
        text: str,
        updated_by: str | None,
        session: AsyncSession | None = None,
    ) -> StoredPlatformPrompt:
        async with use_session(self._sessions, session) as s:
            existing = (
                await s.execute(
                    select(PlatformPromptRow).where(
                        PlatformPromptRow.id == PLATFORM_PROMPT_SINGLETON_ID
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                row = PlatformPromptRow(
                    id=PLATFORM_PROMPT_SINGLETON_ID,
                    text=text,
                    updated_by=updated_by,
                )
                s.add(row)
            else:
                row = existing
                row.text = text
                row.updated_by = updated_by
                # Set the timestamp explicitly instead of relying on the
                # column's `onupdate=utcnow`: that only fires when SQLAlchemy
                # sees the instance as dirty, so re-saving an identical text
                # emitted no UPDATE at all and the admin page's "last updated"
                # line kept reporting the previous save. An admin who re-saves
                # deliberately (confirming the current wording, say) has acted,
                # and the audit line should say so.
                row.updated_at = utcnow()
            # Flush so the insert path's Python-side `default` (utcnow)
            # populates `row.updated_at` before this method returns it — the
            # commit at `use_session`'s exit alone wouldn't hand the value back
            # to this local variable. Same reasoning as
            # `PlatformModelBindingStore._set_once`.
            await s.flush()
            updated_at = row.updated_at
        return StoredPlatformPrompt(
            text=text, updated_by=updated_by, updated_at=updated_at
        )
