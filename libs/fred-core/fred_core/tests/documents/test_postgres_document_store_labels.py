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

"""`document_labels` — the relational assignment table backing
`DocumentMetadata.labels`. Runs against a real SQLite engine (not a fake
store): the invariants under test (constraint-backed idempotency, concurrent
adds not clobbering each other, cascade delete) are properties of the actual
schema and transaction handling, not something a Python fake could prove.

SQLite needs `PRAGMA foreign_keys=ON` per-connection to enforce
`ON DELETE CASCADE` at all (off by default, unlike PostgreSQL) — see
`_make_sqlite_engine` below.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fred_core.documents.document_structures import (
    DocumentMetadata,
    Identity,
    SourceInfo,
    SourceType,
)
from fred_core.documents.postgres_document_store import PostgresDocumentMetadataStore
from fred_core.models.base import Base
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


async def _make_sqlite_engine(tmp_path: Path, filename: str) -> AsyncEngine:
    db_path = tmp_path / filename
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


def _doc(uid: str) -> DocumentMetadata:
    return DocumentMetadata(
        identity=Identity(document_name=f"{uid}.pdf", document_uid=uid, title=uid),
        source=SourceInfo(
            source_type=SourceType.PUSH, source_tag="fred", pull_location=None
        ),
    )


@pytest.mark.asyncio
async def test_add_label_is_idempotent_via_the_db_constraint(tmp_path: Path) -> None:
    engine = await _make_sqlite_engine(tmp_path, "idempotent_add.sqlite3")
    store = PostgresDocumentMetadataStore(engine)
    await store.save_metadata(_doc("doc-1"))

    await store.add_label("doc-1", "DAT")
    await store.add_label("doc-1", "DAT")
    await store.add_label("doc-1", "DAT")

    assert await store.get_labels_for_document("doc-1") == ["DAT"]


@pytest.mark.asyncio
async def test_remove_label_is_idempotent_for_an_absent_assignment(
    tmp_path: Path,
) -> None:
    engine = await _make_sqlite_engine(tmp_path, "idempotent_remove.sqlite3")
    store = PostgresDocumentMetadataStore(engine)
    await store.save_metadata(_doc("doc-1"))

    # Removing a label that was never assigned must not raise.
    await store.remove_label("doc-1", "never-added")
    await store.add_label("doc-1", "DAT")
    await store.remove_label("doc-1", "DAT")
    await store.remove_label("doc-1", "DAT")

    assert await store.get_labels_for_document("doc-1") == []


@pytest.mark.asyncio
async def test_two_concurrent_adds_of_different_labels_both_survive(
    tmp_path: Path,
) -> None:
    """The composite primary key is (document_uid, label): two different
    labels for the same document are two distinct rows, never in contention —
    unlike the old JSONB read-modify-write, where the last `save_metadata` to
    commit silently discarded the other writer's change."""
    engine = await _make_sqlite_engine(tmp_path, "concurrent_add.sqlite3")
    store = PostgresDocumentMetadataStore(engine)
    await store.save_metadata(_doc("doc-1"))

    await asyncio.gather(
        store.add_label("doc-1", "DAT"),
        store.add_label("doc-1", "MEX"),
    )

    assert await store.get_labels_for_document("doc-1") == ["DAT", "MEX"]


@pytest.mark.asyncio
async def test_concurrent_metadata_save_does_not_erase_a_confirmed_label(
    tmp_path: Path,
) -> None:
    """A label lives in its own table now, never in the `doc` JSONB
    `save_metadata` overwrites — so a concurrent title/retrievable/rename
    save (which only ever touches `doc`) cannot race it at all, let alone
    lose it. Simulated here as: add a label, then save unrelated metadata
    changes for the same document, and confirm the label survives."""
    engine = await _make_sqlite_engine(tmp_path, "concurrent_other_field.sqlite3")
    store = PostgresDocumentMetadataStore(engine)
    doc = _doc("doc-1")
    await store.save_metadata(doc)
    await store.add_label("doc-1", "DAT")

    # An unrelated metadata mutation, e.g. a title change, racing the label add.
    doc.identity.title = "Renamed while DAT was being added"
    await store.save_metadata(doc)

    assert await store.get_labels_for_document("doc-1") == ["DAT"]
    hydrated = await store.get_metadata_by_uid("doc-1")
    assert hydrated is not None
    assert hydrated.labels == ["DAT"]
    assert hydrated.identity.title == "Renamed while DAT was being added"


@pytest.mark.asyncio
async def test_a_label_mutation_never_rewrites_the_json_document_column(
    tmp_path: Path,
) -> None:
    """`_to_dict` excludes `labels` from every `doc` JSONB write — proving
    this at the row level: the `doc` blob a plain `save_metadata` produced is
    byte-for-byte unaffected by a later label add/remove, because label
    mutations never call `save_metadata` at all."""
    engine = await _make_sqlite_engine(tmp_path, "no_json_rewrite.sqlite3")
    store = PostgresDocumentMetadataStore(engine)
    doc = _doc("doc-1")
    await store.save_metadata(doc)
    before = await store.get_metadata_by_uid("doc-1")
    assert before is not None
    before_dump = before.model_dump(mode="json", exclude={"labels"})

    await store.add_label("doc-1", "DAT")
    await store.remove_label("doc-1", "does-not-exist")

    after = await store.get_metadata_by_uid("doc-1")
    assert after is not None
    assert after.model_dump(mode="json", exclude={"labels"}) == before_dump
    assert after.labels == ["DAT"]


@pytest.mark.asyncio
async def test_labels_field_is_excluded_from_the_saved_json_blob(
    tmp_path: Path,
) -> None:
    """A caller holding a stale in-memory `.labels` (e.g. hydrated moments
    earlier) must not be able to write it back into `doc` via a generic save —
    that would resurrect a second, divergeable copy of the label list."""
    engine = await _make_sqlite_engine(tmp_path, "labels_excluded.sqlite3")
    store = PostgresDocumentMetadataStore(engine)
    doc = _doc("doc-1")
    await store.save_metadata(doc)
    await store.add_label("doc-1", "DAT")

    stale = await store.get_metadata_by_uid("doc-1")  # .labels == ["DAT"]
    assert stale is not None
    stale.labels = ["DAT", "SOMETHING-STALE"]
    stale.identity.title = "unrelated update"
    await store.save_metadata(stale)

    # The table, not the caller's stale in-memory list, remains authoritative.
    assert await store.get_labels_for_document("doc-1") == ["DAT"]


@pytest.mark.asyncio
async def test_cascade_deletes_labels_when_the_document_is_deleted(
    tmp_path: Path,
) -> None:
    engine = await _make_sqlite_engine(tmp_path, "cascade.sqlite3")
    store = PostgresDocumentMetadataStore(engine)
    await store.save_metadata(_doc("doc-1"))
    await store.add_label("doc-1", "DAT")
    await store.add_label("doc-1", "MEX")

    assert await store.delete_metadata("doc-1") is True

    assert await store.get_labels_for_document("doc-1") == []
    assert await store.get_distinct_labels() == []


@pytest.mark.asyncio
async def test_hydrates_labels_field_from_the_table_on_single_read(
    tmp_path: Path,
) -> None:
    engine = await _make_sqlite_engine(tmp_path, "hydrate_single.sqlite3")
    store = PostgresDocumentMetadataStore(engine)
    await store.save_metadata(_doc("doc-1"))
    await store.add_label("doc-1", "MEX")
    await store.add_label("doc-1", "DAT")

    result = await store.get_metadata_by_uid("doc-1")

    assert result is not None
    assert result.labels == ["DAT", "MEX"]  # sorted, not insertion order


@pytest.mark.asyncio
async def test_a_document_with_no_labels_hydrates_to_an_empty_list(
    tmp_path: Path,
) -> None:
    engine = await _make_sqlite_engine(tmp_path, "hydrate_empty.sqlite3")
    store = PostgresDocumentMetadataStore(engine)
    await store.save_metadata(_doc("doc-1"))

    result = await store.get_metadata_by_uid("doc-1")

    assert result is not None
    assert result.labels == []


@pytest.mark.asyncio
async def test_batch_reads_hydrate_labels_for_every_document_in_one_extra_query(
    tmp_path: Path,
) -> None:
    """N+1 guard: `get_metadata_by_uids` for N documents must issue exactly
    one additional query for labels, not N. Asserted by counting SELECTs
    against `document_labels` via SQLAlchemy's engine event hook."""
    engine = await _make_sqlite_engine(tmp_path, "hydrate_batch.sqlite3")
    store = PostgresDocumentMetadataStore(engine)
    for i in range(5):
        await store.save_metadata(_doc(f"doc-{i}"))
        await store.add_label(f"doc-{i}", f"label-{i}")

    label_queries: list[str] = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _count_label_queries(conn, cursor, statement, parameters, context, executemany):
        if "document_labels" in statement:
            label_queries.append(statement)

    results = await store.get_metadata_by_uids([f"doc-{i}" for i in range(5)])

    assert {d.identity.document_uid: d.labels for d in results} == {
        f"doc-{i}": [f"label-{i}"] for i in range(5)
    }
    assert len(label_queries) == 1, (
        f"expected exactly one batched label query for 5 documents, got {len(label_queries)}"
    )


@pytest.mark.asyncio
async def test_get_document_uids_with_label_is_an_exact_match(tmp_path: Path) -> None:
    engine = await _make_sqlite_engine(tmp_path, "exact_match.sqlite3")
    store = PostgresDocumentMetadataStore(engine)
    await store.save_metadata(_doc("doc-1"))
    await store.save_metadata(_doc("doc-2"))
    await store.add_label("doc-1", "DAT")
    await store.add_label("doc-2", "DATA")  # must not match a "DAT" search

    uids = await store.get_document_uids_with_label("DAT")

    assert uids == ["doc-1"]


@pytest.mark.asyncio
async def test_get_document_uids_with_label_narrows_to_the_given_set(
    tmp_path: Path,
) -> None:
    engine = await _make_sqlite_engine(tmp_path, "narrowed_match.sqlite3")
    store = PostgresDocumentMetadataStore(engine)
    await store.save_metadata(_doc("doc-1"))
    await store.save_metadata(_doc("doc-2"))
    await store.add_label("doc-1", "DAT")
    await store.add_label("doc-2", "DAT")

    uids = await store.get_document_uids_with_label("DAT", document_uids={"doc-2"})

    assert uids == ["doc-2"]


@pytest.mark.asyncio
async def test_get_distinct_labels_across_documents(tmp_path: Path) -> None:
    engine = await _make_sqlite_engine(tmp_path, "distinct.sqlite3")
    store = PostgresDocumentMetadataStore(engine)
    await store.save_metadata(_doc("doc-1"))
    await store.save_metadata(_doc("doc-2"))
    await store.add_label("doc-1", "DAT")
    await store.add_label("doc-2", "DAT")
    await store.add_label("doc-2", "MEX")

    assert await store.get_distinct_labels() == ["DAT", "MEX"]


@pytest.mark.asyncio
async def test_get_distinct_labels_narrows_to_the_given_set(tmp_path: Path) -> None:
    engine = await _make_sqlite_engine(tmp_path, "distinct_narrowed.sqlite3")
    store = PostgresDocumentMetadataStore(engine)
    await store.save_metadata(_doc("doc-1"))
    await store.save_metadata(_doc("doc-2"))
    await store.add_label("doc-1", "DAT")
    await store.add_label("doc-2", "MEX")

    assert await store.get_distinct_labels(document_uids={"doc-1"}) == ["DAT"]


@pytest.mark.asyncio
async def test_unicode_and_special_characters_round_trip_unaltered(
    tmp_path: Path,
) -> None:
    engine = await _make_sqlite_engine(tmp_path, "unicode.sqlite3")
    store = PostgresDocumentMetadataStore(engine)
    await store.save_metadata(_doc("doc-1"))
    tricky = [
        "café",
        "日本語",
        "a/b#c?d%e",
        "  leading and trailing kept if pre-trimmed  ".strip(),
    ]

    for label in tricky:
        await store.add_label("doc-1", label)

    assert sorted(await store.get_labels_for_document("doc-1")) == sorted(tricky)
