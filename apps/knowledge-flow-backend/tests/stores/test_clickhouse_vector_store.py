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

from typing import Any, cast

import pytest
from langchain_community.embeddings import FakeEmbeddings
from sqlalchemy import Column, MetaData, String, Table
from sqlalchemy.engine import Engine

import knowledge_flow_backend.core.stores.vector.clickhouse_vector_store as clickhouse_module
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


def test_chunk_read_uses_the_updated_tag_column_when_json_is_stale(monkeypatch: pytest.MonkeyPatch):
    client = _FakeClient()
    store = _store(client)
    store._sa_table = Table(
        "vectors",
        MetaData(),
        Column("chunk_uid", String),
        Column("document_uid", String),
        Column("text", String),
        Column("metadata", String),
        Column("retrievable", String),
        Column("tag_ids", String),
    )
    store._sa_engine = cast(Engine, object())

    class FakeSession:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def __enter__(self) -> "FakeSession":
            return self

        def __exit__(self, *_args: Any) -> None:
            pass

        def execute(self, stmt: Any) -> Any:
            assert "tag_ids" in stmt.selected_columns.keys()

            class Result:
                def all(self) -> list[tuple[str, str, str, int, list[str]]]:
                    return [("chunk-1", "text", '{"tag_ids":["alpha"]}', 1, client.commands[-1][1]["tag_ids"])]

            return Result()

    monkeypatch.setattr(clickhouse_module, "Session", FakeSession)
    store.set_document_tag_ids(document_uid="doc-1", tag_ids=["beta"])

    assert store.get_chunk("doc-1", "chunk-1")["metadata"]["tag_ids"] == ["beta"]
    assert store.get_chunks_for_document("doc-1")[0]["metadata"]["tag_ids"] == ["beta"]
    hits = store._build_ann_hits([("chunk-1", "text", '{"tag_ids":["alpha"]}', 1, ["beta"], 0.9)])
    assert hits[0].document.metadata["tag_ids"] == ["beta"]
