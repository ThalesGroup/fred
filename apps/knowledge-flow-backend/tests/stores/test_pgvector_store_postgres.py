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

"""`PgVectorStoreAdapter` retrievability against a real PostgreSQL with pgvector:
the JSONB update and the search that reads it back, through the same LangChain
store a deployment uses.

Needs the `vector` extension, which `scripts/docker-compose.postgres.yml` does
not provide; point FRED_PGVECTOR_DSN at a disposable pgvector database, e.g.

    docker run -d --rm -p 5434:5432 -e POSTGRES_PASSWORD=test pgvector/pgvector:pg15
    FRED_PGVECTOR_DSN=postgresql://postgres:test@localhost:5434/postgres \\
        .venv/bin/pytest tests/stores/test_pgvector_store_postgres.py -m integration
"""

from __future__ import annotations

import os
import uuid
from typing import Iterator

import pytest
from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding
from sqlalchemy import create_engine, text

from knowledge_flow_backend.core.stores.vector.base_vector_store import CHUNK_ID_FIELD, SearchFilter
from knowledge_flow_backend.core.stores.vector.pgvector_store import PgVectorStoreAdapter

pytestmark = [pytest.mark.integration, pytest.mark.integration_postgres]

_DEFAULT_DSN = "postgresql://test:test@localhost:5433/test_migrations"  # pragma: allowlist secret


@pytest.fixture
def store() -> Iterator[PgVectorStoreAdapter]:
    dsn = os.environ.get("FRED_PGVECTOR_DSN", _DEFAULT_DSN)
    try:
        with create_engine(dsn).begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    except Exception as exc:
        pytest.skip(f"no pgvector database at {dsn}: {exc}")
    adapter = PgVectorStoreAdapter(
        embedding_model=DeterministicFakeEmbedding(size=16),
        embedding_model_name="fake",
        connection_string=dsn,
        collection_name=f"retrievable-{uuid.uuid4().hex}",
    )
    try:
        yield adapter
    finally:
        adapter._vs.delete_collection()


def _chunks(document_uid: str, count: int) -> list[Document]:
    return [
        Document(
            page_content=f"retrievability probe chunk {i} of {document_uid}",
            metadata={CHUNK_ID_FIELD: f"{document_uid}::chunk::{i}", "document_uid": document_uid, "chunk_index": i, "retrievable": True},
        )
        for i in range(count)
    ]


def _searchable_uids(store: PgVectorStoreAdapter) -> set[str]:
    hits = store.ann_search("retrievability probe", k=10, search_filter=SearchFilter(metadata_terms={"retrievable": [True]}))
    return {h.document.metadata["document_uid"] for h in hits}


def test_toggle_round_trip_controls_search_visibility(store: PgVectorStoreAdapter) -> None:
    store.add_documents(_chunks("doc-a", 2) + _chunks("doc-b", 2))
    assert _searchable_uids(store) == {"doc-a", "doc-b"}

    store.set_document_retrievable(document_uid="doc-a", value=False)

    assert {c["metadata"]["retrievable"] for c in store.get_chunks_for_document("doc-a")} == {False}
    assert {c["metadata"]["retrievable"] for c in store.get_chunks_for_document("doc-b")} == {True}
    assert _searchable_uids(store) == {"doc-b"}

    store.set_document_retrievable(document_uid="doc-a", value=True)

    assert {c["metadata"]["retrievable"] for c in store.get_chunks_for_document("doc-a")} == {True}
    assert _searchable_uids(store) == {"doc-a", "doc-b"}


def test_legacy_chunk_without_the_field_stays_searchable_until_toggled(store: PgVectorStoreAdapter) -> None:
    legacy = _chunks("doc-old", 1)
    del legacy[0].metadata["retrievable"]
    store.add_documents(legacy)
    assert _searchable_uids(store) == {"doc-old"}

    store.set_document_retrievable(document_uid="doc-old", value=False)

    assert _searchable_uids(store) == set()
