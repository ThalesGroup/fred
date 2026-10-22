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

from typing import Any

import pytest
from langchain_community.embeddings import FakeEmbeddings

from knowledge_flow_backend.core.stores.vector.clickhouse_vector_store import ClickHouseVectorStoreAdapter


class _FakeClient:
    def __init__(self, *, fails: bool = False) -> None:
        self.fails = fails
        self.commands: list[tuple[str, dict[str, Any]]] = []

    def command(self, sql: str, parameters: dict[str, Any] | None = None) -> None:
        if self.fails:
            raise RuntimeError("mutation rejected")
        self.commands.append((sql, parameters or {}))


def _store(client: _FakeClient) -> ClickHouseVectorStoreAdapter:
    store = ClickHouseVectorStoreAdapter(
        embedding_model=FakeEmbeddings(size=4),
        embedding_model_name="fake",
        host="localhost",
        database="fred",
        table="vectors",
        username="",
        password="",
    )
    store._ch = client
    return store


def test_set_document_tag_ids_rewrites_the_column_search_filters_on():
    client = _FakeClient()
    store = _store(client)

    store.set_document_tag_ids(document_uid="doc-1", tag_ids=["alpha", "beta"])

    [(sql, params)] = client.commands
    assert sql.startswith("ALTER TABLE fred.vectors UPDATE tag_ids = {tag_ids:Array(String)} WHERE document_uid = {doc_uid:String}")
    assert params == {"tag_ids": ["alpha", "beta"], "doc_uid": "doc-1"}


def test_set_document_tag_ids_propagates_a_failed_mutation():
    with pytest.raises(RuntimeError, match="mutation rejected"):
        _store(_FakeClient(fails=True)).set_document_tag_ids(document_uid="doc-1", tag_ids=["beta"])
