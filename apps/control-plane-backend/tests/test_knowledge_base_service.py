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
`control_plane_backend.knowledge_base.service.create_knowledge_base` (docs/swift/rfc/KNOWLEDGE-BASE-RFC.md
§2/§4/§6) — the two independent fail-closed checks (unknown/parked type,
then team not `can_use`-authorized), against a real SQLite-backed store.
"""

from __future__ import annotations

import pytest
from control_plane_backend.knowledge_base.service import (
    KnowledgeBaseTypeAccessDenied,
    KnowledgeBaseTypeNotFound,
    create_knowledge_base,
)
from control_plane_backend.knowledge_base.store import KnowledgeBaseStore
from control_plane_backend.knowledge_base_types.catalog import (
    ConfiguredKnowledgeBaseTypeCatalogSource,
    KnowledgeBaseTypeConfig,
)
from control_plane_backend.models.base import Base
from control_plane_backend.models.knowledge_base_models import KnowledgeBaseRow
from fred_core.common import TeamId
from fred_core.security.rebac.noop_engine import NoopRebacEngine
from fred_sdk.contracts.knowledge_base import KnowledgeBaseKind, KnowledgeBaseMode
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.asyncio


class _DenyingRebacEngine(NoopRebacEngine):
    """`NoopRebacEngine` always permits; this override always denies."""

    async def has_permission(self, *args, **kwargs) -> bool:  # type: ignore[override]
        return False


def _knowledge_base_type_source(
    *, enabled: bool = True
) -> ConfiguredKnowledgeBaseTypeCatalogSource:
    return ConfiguredKnowledgeBaseTypeCatalogSource(
        (
            KnowledgeBaseTypeConfig(
                knowledge_base_type_id="local_fs_rag",
                name="Local filesystem knowledge base",
                kind=KnowledgeBaseKind.RAG_SQL,
                mode=KnowledgeBaseMode.PULL,
                connector_kind="local_fs",
                enabled=enabled,
            ),
        )
    )


async def _make_store() -> KnowledgeBaseStore:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[KnowledgeBaseRow.__table__],  # type: ignore[list-item]
        )
    return KnowledgeBaseStore(engine)


async def test_create_knowledge_base_succeeds_when_type_enabled_and_team_authorized() -> (
    None
):
    store = await _make_store()

    knowledge_base = await create_knowledge_base(
        rebac=NoopRebacEngine(),
        store=store,
        catalog_source=_knowledge_base_type_source(),
        team_id=TeamId("team-1"),
        knowledge_base_type_id="local_fs_rag",
        name="Team FS knowledge base",
        tag_ids=["tag-a"],
        connector_ref="/home/team/docs",
    )

    assert knowledge_base.knowledge_base_type_id == "local_fs_rag"
    assert await store.get(knowledge_base.knowledge_base_id) == knowledge_base


async def test_create_knowledge_base_rejects_unknown_knowledge_base_type() -> None:
    store = await _make_store()

    with pytest.raises(KnowledgeBaseTypeNotFound):
        await create_knowledge_base(
            rebac=NoopRebacEngine(),
            store=store,
            catalog_source=_knowledge_base_type_source(),
            team_id=TeamId("team-1"),
            knowledge_base_type_id="unknown_type",
            name="Team FS knowledge base",
            tag_ids=[],
            connector_ref=None,
        )


async def test_create_knowledge_base_rejects_parked_knowledge_base_type() -> None:
    store = await _make_store()

    with pytest.raises(KnowledgeBaseTypeNotFound):
        await create_knowledge_base(
            rebac=NoopRebacEngine(),
            store=store,
            catalog_source=_knowledge_base_type_source(enabled=False),
            team_id=TeamId("team-1"),
            knowledge_base_type_id="local_fs_rag",
            name="Team FS knowledge base",
            tag_ids=[],
            connector_ref=None,
        )


async def test_create_knowledge_base_fails_closed_when_team_not_authorized() -> None:
    store = await _make_store()

    with pytest.raises(KnowledgeBaseTypeAccessDenied):
        await create_knowledge_base(
            rebac=_DenyingRebacEngine(),
            store=store,
            catalog_source=_knowledge_base_type_source(),
            team_id=TeamId("team-1"),
            knowledge_base_type_id="local_fs_rag",
            name="Team FS knowledge base",
            tag_ids=[],
            connector_ref=None,
        )
