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
`documents_total` team scoping (NOTES-OBSERV-02-FOLLOWUPS.md #1). Before this
fix, the router rejected any `team_id` for this preset with 400, breaking
`TeamUsagePage`'s "Team usage: documents" widget (§2.5) even though
`DocumentMetadataRow` has always been reachable via tag ownership. This suite
covers the two behaviors the router (`kpi/api.py`) depends on: the flag it
gates on, and `_count_all_documents`'s routing between the platform-wide and
team-scoped counts — the one piece of new logic, independent of OpenSearch
(covered separately for the array-join itself in fred-core's
`test_postgres_document_store_count_by_team.py`).
"""

# pyright: reportArgumentType=false
# ^ this suite passes `request=None` — `_count_all_documents` only forwards it
#   to `get_application_container`, which is monkeypatched here to ignore it
#   — same convention as test_kpi_storage_and_activity.py.
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from control_plane_backend.kpi.presets import documents_total
from control_plane_backend.kpi.presets.documents_total import (
    DOCUMENTS_TOTAL_PRESET,
    _count_all_documents,
)
from fred_core.common import TeamId
from fred_core.documents.document_structures import (
    DocumentMetadata,
    Identity,
    SourceInfo,
    SourceType,
    Tagging,
)
from fred_core.documents.postgres_document_store import PostgresDocumentMetadataStore
from fred_core.documents.tag_models import TagRow
from fred_core.models.base import Base
from fred_core.sql.async_session import make_session_factory
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def test_documents_total_preset_is_team_scopable() -> None:
    """Regression guard: the store-layer count_by_team gap
    (NOTES-OBSERV-02-FOLLOWUPS.md #1) is fixed, so the router must accept a
    team_id for this preset instead of rejecting it with 400."""
    assert DOCUMENTS_TOTAL_PRESET.team_scopable is True


async def _make_sqlite_engine(tmp_path: Path, filename: str) -> AsyncEngine:
    db_path = tmp_path / filename
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


@pytest.mark.asyncio
async def test_count_all_documents_routes_to_platform_wide_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = await _make_sqlite_engine(tmp_path, "docs_platform.sqlite3")
    sessions = make_session_factory(engine)
    async with sessions() as s:
        async with s.begin():
            s.add(TagRow(tag_id="tag-a", owner_id="team-1"))
            s.add(TagRow(tag_id="tag-b", owner_id="team-2"))

    store = PostgresDocumentMetadataStore(engine)
    await store.save_metadata(
        DocumentMetadata(
            identity=Identity(document_name="d1.pdf", document_uid="d1", title="d1"),
            source=SourceInfo(
                source_type=SourceType.PUSH, source_tag="uploads", pull_location=None
            ),
            tags=Tagging(tag_ids=["tag-a"]),
        )
    )
    await store.save_metadata(
        DocumentMetadata(
            identity=Identity(document_name="d2.pdf", document_uid="d2", title="d2"),
            source=SourceInfo(
                source_type=SourceType.PUSH, source_tag="uploads", pull_location=None
            ),
            tags=Tagging(tag_ids=["tag-b"]),
        )
    )

    monkeypatch.setattr(
        documents_total,
        "get_application_container",
        lambda request: SimpleNamespace(get_pg_async_engine=lambda: engine),
    )

    assert await _count_all_documents(request=None, team_id=None) == 2
    assert await _count_all_documents(request=None, team_id=TeamId("team-1")) == 1
    assert await _count_all_documents(request=None, team_id=TeamId("team-2")) == 1
