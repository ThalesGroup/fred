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

Use a disposable database initialized with deploy/postgres/bootstrap.sql, and
set FRED_PGVECTOR_DSN to its fred_kf login through a protected environment.
The fixture never creates an extension or uses an administrator login.
"""

from __future__ import annotations

import os
import uuid
from typing import Iterator

import pytest
from fred_core.common import PostgresStoreConfig
from fred_core.sql.base_sql import create_engine_from_config
from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding
from sqlalchemy import text
from sqlalchemy.engine import make_url

from fred_knowledge.vector.base_vector_store import CHUNK_ID_FIELD, SearchFilter
from fred_knowledge.vector.pgvector_store import PgVectorStoreAdapter

pytestmark = [pytest.mark.integration, pytest.mark.integration_postgres]


@pytest.fixture
def store() -> Iterator[PgVectorStoreAdapter]:
    dsn = os.environ.get("FRED_PGVECTOR_DSN")
    if not dsn:
        pytest.skip("Set FRED_PGVECTOR_DSN to a bootstrapped disposable fred_kf database")
    url = make_url(dsn)
    assert url.username == "fred_kf", "The integration fixture must use the consumer login"
    config = PostgresStoreConfig(host=url.host, port=url.port or 5432, username=url.username, password=url.password, database=url.database, schema="knowledge")
    engine = create_engine_from_config(config)
    try:
        with engine.connect() as conn:
            assert conn.scalar(text("select current_schema()")) == "knowledge"
            assert conn.scalar(text("select to_regtype('knowledge.vector') is not null"))
    finally:
        engine.dispose()
    adapter = PgVectorStoreAdapter(
        embedding_model=DeterministicFakeEmbedding(size=16),
        embedding_model_name="fake",
        postgres_config=config,
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
