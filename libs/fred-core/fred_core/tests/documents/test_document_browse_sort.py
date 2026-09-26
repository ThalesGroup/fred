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

"""Ordering of a paginated tag browse.

Two halves, because the store has two branches. The Python ordering
(`sort_documents`) is what the SQLite path and the base store use, and it runs
here. The PostgreSQL ORDER BY is only *compiled* here — SQLite never executes
it, the same gap `tests/integration/test_postgres_document_store_sql.py`
documents after it once shipped a production failure — so a real execution
test lives beside that one.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fred_core.documents.document_store import sort_documents
from fred_core.documents.document_structures import (
    DocumentMetadata,
    FileInfo,
    Identity,
    SourceInfo,
    SourceType,
    Tagging,
)
from fred_core.documents.postgres_document_store import PostgresDocumentMetadataStore
from fred_core.models.base import Base
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


async def _make_sqlite_engine(tmp_path: Path, filename: str) -> AsyncEngine:
    db_path = tmp_path / filename
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


def _doc(
    uid: str,
    name: str,
    *,
    day: int = 1,
    size: int | None = 100,
    tag_ids: list[str] | None = None,
) -> DocumentMetadata:
    return DocumentMetadata(
        identity=Identity(document_name=name, document_uid=uid, title=name),
        source=SourceInfo(
            source_type=SourceType.PUSH,
            source_tag="uploads",
            pull_location=None,
            date_added_to_kb=datetime(2026, 1, day, tzinfo=timezone.utc),
        ),
        file=FileInfo(file_size_bytes=size),
        tags=Tagging(tag_ids=tag_ids if tag_ids is not None else ["tag-a"]),
    )


def _names(docs: list[DocumentMetadata]) -> list[str]:
    return [doc.identity.document_name for doc in docs]


class TestPythonOrdering:
    def test_name_ascending_ignores_case(self) -> None:
        # An ASCII sort files every capital before every lowercase, so "annexe"
        # would land after "Zebra" — which reads as broken in a file list.
        docs = [_doc("1", "Zebra.pdf"), _doc("2", "annexe.pdf"), _doc("3", "Beta.pdf")]

        assert _names(sort_documents(docs, "name", "asc")) == [
            "annexe.pdf",
            "Beta.pdf",
            "Zebra.pdf",
        ]

    def test_name_descending_is_the_exact_mirror(self) -> None:
        docs = [_doc("1", "Zebra.pdf"), _doc("2", "annexe.pdf"), _doc("3", "Beta.pdf")]

        assert _names(sort_documents(docs, "name", "desc")) == [
            "Zebra.pdf",
            "Beta.pdf",
            "annexe.pdf",
        ]

    def test_created_orders_by_date_added(self) -> None:
        docs = [
            _doc("1", "c.pdf", day=3),
            _doc("2", "a.pdf", day=1),
            _doc("3", "b.pdf", day=2),
        ]

        assert _names(sort_documents(docs, "created", "desc")) == [
            "c.pdf",
            "b.pdf",
            "a.pdf",
        ]

    def test_size_orders_numerically_not_as_text(self) -> None:
        # The SQL side casts to BigInteger for this reason; a text comparison
        # would file 1000 between 100 and 20.
        docs = [
            _doc("1", "a.pdf", size=100),
            _doc("2", "b.pdf", size=1000),
            _doc("3", "c.pdf", size=20),
        ]

        assert _names(sort_documents(docs, "size", "asc")) == [
            "c.pdf",
            "a.pdf",
            "b.pdf",
        ]

    def test_a_document_without_a_size_sorts_last_ascending(self) -> None:
        docs = [_doc("1", "a.pdf", size=None), _doc("2", "b.pdf", size=5)]

        assert _names(sort_documents(docs, "size", "asc")) == ["b.pdf", "a.pdf"]

    def test_and_first_descending_like_postgresql_itself(self) -> None:
        docs = [_doc("1", "a.pdf", size=None), _doc("2", "b.pdf", size=5)]

        assert _names(sort_documents(docs, "size", "desc")) == ["a.pdf", "b.pdf"]

    def test_equal_values_are_broken_by_uid_so_paging_stays_total(self) -> None:
        # Without a total order the same document can appear on two pages, or
        # on none, as the reader pages through.
        tied = [_doc("c", "same.pdf"), _doc("a", "same.pdf"), _doc("b", "same.pdf")]

        ordered = sort_documents(tied, "name", "asc")

        assert [doc.identity.document_uid for doc in ordered] == ["a", "b", "c"]


class TestCompiledPostgresOrdering:
    """The ORDER BY SQLite never runs. Compiled, not executed — an execution
    test needs a real PostgreSQL and lives in the integration suite."""

    def _sql(self, sort_by: str, sort_order: str) -> str:
        store = PostgresDocumentMetadataStore.__new__(PostgresDocumentMetadataStore)
        return " ".join(
            str(term.compile(compile_kwargs={"literal_binds": True}))
            for term in store._browse_order_by(sort_by, sort_order)  # type: ignore[arg-type]
        )

    def test_name_reads_the_displayed_file_name_from_the_json_blob(self) -> None:
        # The table shows identity.document_name; ordering on `title` would sort
        # the list by something the reader cannot see.
        sql = self._sql("name", "asc")

        assert "identity" in sql and "document_name" in sql
        assert "lower" in sql.lower()

    def test_created_uses_the_real_column(self) -> None:
        assert "date_added_to_kb" in self._sql("created", "asc")

    def test_size_casts_out_of_the_json_blob(self) -> None:
        sql = self._sql("size", "asc")

        assert "file_size_bytes" in sql
        assert "BIGINT" in sql.upper()

    @pytest.mark.parametrize("sort_by", ["name", "created", "size"])
    @pytest.mark.parametrize("sort_order", ["asc", "desc"])
    def test_every_ordering_ends_on_the_uid_tie_break(
        self, sort_by: str, sort_order: str
    ) -> None:
        sql = self._sql(sort_by, sort_order)

        assert "document_uid" in sql
        assert sql.count("DESC") == (2 if sort_order == "desc" else 0)


@pytest.mark.asyncio
async def test_browse_applies_the_order_before_cutting_the_page(tmp_path: Path) -> None:
    """The point of ordering store-side: page 1 must hold the first documents
    of the whole tag, not the first the store happened to return."""
    engine = await _make_sqlite_engine(tmp_path, "browse_sort.sqlite3")
    store = PostgresDocumentMetadataStore(engine)
    for uid, name in [
        ("1", "delta.pdf"),
        ("2", "alpha.pdf"),
        ("3", "charlie.pdf"),
        ("4", "bravo.pdf"),
    ]:
        await store.save_metadata(_doc(uid, name))

    page, total = await store.browse_metadata_in_tag(
        "tag-a", offset=0, limit=2, sort_by="name", sort_order="asc"
    )

    assert total == 4
    assert _names(page) == ["alpha.pdf", "bravo.pdf"]


@pytest.mark.asyncio
async def test_browse_defaults_to_name_ascending(tmp_path: Path) -> None:
    engine = await _make_sqlite_engine(tmp_path, "browse_sort_default.sqlite3")
    store = PostgresDocumentMetadataStore(engine)
    await store.save_metadata(_doc("1", "beta.pdf"))
    await store.save_metadata(_doc("2", "alpha.pdf"))

    page, _ = await store.browse_metadata_in_tag("tag-a")

    assert _names(page) == ["alpha.pdf", "beta.pdf"]


@pytest.mark.asyncio
async def test_paging_through_a_sorted_tag_never_repeats_a_document(
    tmp_path: Path,
) -> None:
    engine = await _make_sqlite_engine(tmp_path, "browse_sort_pages.sqlite3")
    store = PostgresDocumentMetadataStore(engine)
    for uid in ["e", "a", "d", "b", "c"]:
        await store.save_metadata(_doc(uid, "same.pdf"))

    seen: list[str] = []
    for offset in (0, 2, 4):
        page, _ = await store.browse_metadata_in_tag("tag-a", offset=offset, limit=2)
        seen.extend(doc.identity.document_uid for doc in page)

    assert seen == ["a", "b", "c", "d", "e"]
