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
`control_plane_backend.corpus.service.create_corpus` (docs/swift/rfc/INDEXED-CORPUS-RFC.md
§2/§4/§6) — the two independent fail-closed checks (unknown/parked type,
then team not `can_use`-authorized), against a real SQLite-backed store.
"""

from __future__ import annotations

import pytest
from control_plane_backend.corpus.service import (
    CorpusTypeAccessDenied,
    CorpusTypeNotFound,
    create_corpus,
)
from control_plane_backend.corpus.store import CorpusStore
from control_plane_backend.corpus_types.catalog import (
    ConfiguredCorpusTypeCatalogSource,
    CorpusTypeConfig,
)
from control_plane_backend.models.base import Base
from control_plane_backend.models.corpus_models import CorpusRow
from fred_core.common import TeamId
from fred_core.security.rebac.noop_engine import NoopRebacEngine
from fred_sdk.contracts.corpus import CorpusKind, CorpusMode
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.asyncio


class _DenyingRebacEngine(NoopRebacEngine):
    """`NoopRebacEngine` always permits; this override always denies."""

    async def has_permission(self, *args, **kwargs) -> bool:  # type: ignore[override]
        return False


def _corpus_type_source(*, enabled: bool = True) -> ConfiguredCorpusTypeCatalogSource:
    return ConfiguredCorpusTypeCatalogSource(
        (
            CorpusTypeConfig(
                corpus_type_id="local_fs_rag",
                name="Local filesystem corpus",
                kind=CorpusKind.RAG_SQL,
                mode=CorpusMode.PULL,
                connector_kind="local_fs",
                enabled=enabled,
            ),
        )
    )


async def _make_store() -> CorpusStore:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[CorpusRow.__table__])  # type: ignore[list-item]
    return CorpusStore(engine)


async def test_create_corpus_succeeds_when_type_enabled_and_team_authorized() -> None:
    store = await _make_store()

    corpus = await create_corpus(
        rebac=NoopRebacEngine(),
        store=store,
        catalog_source=_corpus_type_source(),
        team_id=TeamId("team-1"),
        corpus_type_id="local_fs_rag",
        name="Team FS corpus",
        tag_ids=["tag-a"],
        connector_ref="/home/team/docs",
    )

    assert corpus.corpus_type_id == "local_fs_rag"
    assert await store.get(corpus.corpus_id) == corpus


async def test_create_corpus_rejects_unknown_corpus_type() -> None:
    store = await _make_store()

    with pytest.raises(CorpusTypeNotFound):
        await create_corpus(
            rebac=NoopRebacEngine(),
            store=store,
            catalog_source=_corpus_type_source(),
            team_id=TeamId("team-1"),
            corpus_type_id="unknown_type",
            name="Team FS corpus",
            tag_ids=[],
            connector_ref=None,
        )


async def test_create_corpus_rejects_parked_corpus_type() -> None:
    store = await _make_store()

    with pytest.raises(CorpusTypeNotFound):
        await create_corpus(
            rebac=NoopRebacEngine(),
            store=store,
            catalog_source=_corpus_type_source(enabled=False),
            team_id=TeamId("team-1"),
            corpus_type_id="local_fs_rag",
            name="Team FS corpus",
            tag_ids=[],
            connector_ref=None,
        )


async def test_create_corpus_fails_closed_when_team_not_authorized() -> None:
    store = await _make_store()

    with pytest.raises(CorpusTypeAccessDenied):
        await create_corpus(
            rebac=_DenyingRebacEngine(),
            store=store,
            catalog_source=_corpus_type_source(),
            team_id=TeamId("team-1"),
            corpus_type_id="local_fs_rag",
            name="Team FS corpus",
            tag_ids=[],
            connector_ref=None,
        )
