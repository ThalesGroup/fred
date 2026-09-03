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

"""
Platform-wide platform prompt.

The distinction these tests exist to pin: **row absent** ("no admin ever saved
one" — pods fall back to their own `config/platform_prompt.json`) is NOT the
same as **row present with an empty string** ("an admin deliberately suppressed
the block"). Every layer has to keep them apart, because collapsing them would
silently resurrect the pod default for an admin who meant to turn the block off.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from control_plane_backend.platform_prompt.schemas import (
    PLATFORM_PROMPT_MAX_CHARS,
    SetPlatformPromptRequest,
)
from control_plane_backend.platform_prompt.service import (
    _to_platform_prompt,
    resolve_platform_prompt_text,
)
from control_plane_backend.platform_prompt.store import StoredPlatformPrompt


class _Store:
    def __init__(self, stored: StoredPlatformPrompt | None) -> None:
        self._stored = stored

    async def get(self) -> StoredPlatformPrompt | None:
        return self._stored


def _deps(stored: StoredPlatformPrompt | None) -> SimpleNamespace:
    return SimpleNamespace(get_platform_prompt_store=lambda: _Store(stored))


# ---------------------------------------------------------------------------
# Projection: absent row vs stored empty string
# ---------------------------------------------------------------------------


def test_absent_row_projects_the_pods_default() -> None:
    # The admin editor must open on the text agents are ACTUALLY receiving.
    # Reporting "" here is what left the page showing a blank box on a fresh
    # deployment, implying no platform prompt was in force when one was.
    projected = _to_platform_prompt(None, pod_default="POD-TEXT")

    assert projected.is_default is True
    assert projected.text == "POD-TEXT"
    assert projected.source_unavailable is False
    assert projected.updated_by is None


def test_absent_row_with_no_reachable_pod_says_so() -> None:
    # An empty editor and "we could not ask any pod" look identical to a reader
    # unless the response distinguishes them. Collapsing the two would tell an
    # admin the deployment has no platform prompt during a pod outage.
    projected = _to_platform_prompt(None, pod_default=None)

    assert projected.is_default is True
    assert projected.text == ""
    assert projected.source_unavailable is True


def test_stored_empty_string_is_not_reported_as_default() -> None:
    # `is_default` must differ from the cases above, AND the pod default must
    # not leak into `text` here — this is the admin who turned the block off,
    # and showing them the pod's default would misreport their own decision
    # back to them.
    projected = _to_platform_prompt(
        StoredPlatformPrompt(text="", updated_by="admin", updated_at=None),
        pod_default="POD-TEXT",
    )

    assert projected.is_default is False
    assert projected.text == ""
    assert projected.source_unavailable is False
    assert projected.updated_by == "admin"


def test_a_saved_row_never_reports_source_unavailable() -> None:
    # A stored value answers on its own, so an unreachable pod is irrelevant to
    # it — flagging it would send the UI into a degraded state for nothing.
    projected = _to_platform_prompt(
        StoredPlatformPrompt(text="MINE", updated_by="admin", updated_at=None),
        pod_default=None,
    )

    assert projected.text == "MINE"
    assert projected.source_unavailable is False


# ---------------------------------------------------------------------------
# Runtime resolution — the value the pod actually receives
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_returns_none_when_no_row_was_ever_saved() -> None:
    # `None` is what makes the pod fall back to its shipped default.
    assert await resolve_platform_prompt_text(_deps(None)) is None  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_resolve_returns_empty_string_for_a_deliberately_cleared_prompt() -> None:
    # Must be `""`, never `None`: `None` would hand the pod default back to an
    # admin who explicitly cleared the prompt.
    stored = StoredPlatformPrompt(text="", updated_by="admin", updated_at=None)

    assert await resolve_platform_prompt_text(_deps(stored)) == ""  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_resolve_returns_the_saved_text_verbatim() -> None:
    # No trimming here: the runtime's `build_platform_prompt_prefix` owns
    # whitespace handling, and doing it in two places would let them disagree.
    stored = StoredPlatformPrompt(
        text="  BE HELPFUL  ", updated_by="admin", updated_at=None
    )

    assert await resolve_platform_prompt_text(_deps(stored)) == "  BE HELPFUL  "  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Request validation
# ---------------------------------------------------------------------------


def test_empty_text_is_a_valid_request() -> None:
    assert SetPlatformPromptRequest(text="").text == ""


def test_text_over_the_cap_is_rejected_at_parsing() -> None:
    with pytest.raises(ValueError):
        SetPlatformPromptRequest(text="x" * (PLATFORM_PROMPT_MAX_CHARS + 1))


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValueError):
        SetPlatformPromptRequest(text="ok", is_default=True)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Timestamp refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resaving_identical_text_still_refreshes_updated_at() -> None:
    """Re-saving the same wording is an action, and the audit line must show it.

    Relying on the column's `onupdate=utcnow` was not enough: it only fires when
    SQLAlchemy considers the instance dirty, so an identical re-save emitted no
    UPDATE and the admin page kept reporting the previous save's timestamp.
    """

    from datetime import datetime, timedelta, timezone

    from control_plane_backend.models.base import Base
    from control_plane_backend.models.platform_prompt_models import PlatformPromptRow
    from control_plane_backend.platform_prompt.store import PlatformPromptStore
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[PlatformPromptRow.__table__],  # type: ignore[list-item]
        )

    store = PlatformPromptStore(engine)
    first = await store.set(text="same", updated_by="admin")
    # Backdate the stored row so an unrefreshed timestamp is unmistakable.
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    stale = datetime.now(timezone.utc) - timedelta(days=1)
    async with sessions() as s:
        row = await s.get(PlatformPromptRow, "default")
        assert row is not None
        row.updated_at = stale
        await s.commit()

    second = await store.set(text="same", updated_by="admin")

    assert second.updated_at is not None
    assert first.updated_at is not None
    assert second.updated_at > stale
    await engine.dispose()
