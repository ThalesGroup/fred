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


import pytest
from fred_core.documents.document_store import BaseDocumentMetadataStore
from fred_core.documents.postgres_document_store import PostgresDocumentMetadataStore
from fred_core.tests.documents.test_document_browse_sort import _doc
from sqlalchemy.dialects import postgresql


class MemoryStore(BaseDocumentMetadataStore):
    def __init__(self, docs):
        self.docs = docs

    async def get_all_metadata(self, filters, session=None):
        return self.docs


@pytest.mark.asyncio
async def test_filter_authorization_and_library_document_union():
    docs = [
        _doc("a", "Report.pdf", tag_ids=["A"]),
        _doc("b", "BUDGET_%.pdf", tag_ids=["B"]),
        _doc("c", "report.pdf", tag_ids=["other"]),
    ]
    docs[0].identity.title = "Budget_% overview"
    store = MemoryStore(docs)
    entries, _ = await store.discover_metadata_page(
        folder_ids=["A", "B"],
        selected_folder_ids=["A"],
        document_uids=["b"],
        readable_uids=["a", "b", "c"],
        name_filter="budget_%",
    )
    assert {entry.document.document_uid for entry in entries} == {"a", "b"}
    entries, _ = await store.discover_metadata_page(
        folder_ids=["A", "B"], readable_uids=["b"], name_filter="budget_%"
    )
    assert [entry.document.document_uid for entry in entries] == ["b"]


@pytest.mark.asyncio
@pytest.mark.parametrize("order", ["asc", "desc"])
async def test_equal_arrivals_unknowns_and_keyset_traversal(order):
    docs = [_doc(uid, uid, tag_ids=["A", "B"]) for uid in ["a", "b", "c", "d"]]
    docs[-1].source.model_fields_set.discard("date_added_to_kb")
    store = MemoryStore(docs)
    seen = []
    position = None
    while True:
        entries, unknown = await store.discover_metadata_page(
            folder_ids=["A", "B"],
            sort_by="added_to_kb",
            sort_order=order,
            limit=1,
            after=position,
        )
        assert unknown
        if not entries:
            break
        entry = entries[0]
        seen.append(entry.document.document_uid)
        position = (entry.sort_value, entry.document.document_uid)
    assert seen == (["a", "b", "c", "d"] if order == "asc" else ["c", "b", "a", "d"])


def test_postgres_query_applies_permissions_before_limit_and_bounds_bind_count():
    query, unknown = PostgresDocumentMetadataStore._discovery_query(
        folder_ids=["A"],
        readable_uids=[str(i) for i in range(40000)],
        name_filter="_%",
        sort_by="added_to_kb",
        sort_order="desc",
        limit=2,
    )
    compiled = query.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "ANY" in sql and "NULLS LAST" in sql and "LIMIT" in sql
    assert "date_added_to_kb" in str(unknown)
    assert len(compiled.params) < 20
    assert any("\\_\\%" in str(value) for value in compiled.params.values())
