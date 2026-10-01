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

"""`PostgresDocumentMetadataStore`'s raw-SQL branches, executed against a real
PostgreSQL.

Every other test of this store runs on SQLite and therefore takes the Python
fallback branch, so the `text(...)` SQL is never executed (a limitation
`tests/documents/test_postgres_document_store_bulk_mark_vector_done.py` calls
out in its own docstring). That gap shipped a real production failure: the
label-mutation UPDATE passed its bind parameters straight into
`jsonb_build_object(...)`, which is variadic `"any"` and gives PostgreSQL no
context to infer a parameter type from -- asyncpg failed at prepare time with
`could not determine data type of parameter $1`, so adding a label to a
document errored out. SQLite can never catch that class of bug.

Run:

    export FRED_PG_DSN="postgresql+asyncpg://fred:Azerty123_@localhost:5432/fred"  # pragma: allowlist secret
    .venv/bin/pytest fred_core/tests/integration/test_postgres_document_store_sql.py -m integration

Each test gets its own throwaway PostgreSQL schema (dropped on teardown), so
this never reads or writes the shared dev database's real tables.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import create_async_engine

from fred_core.documents.document_models import DocumentMetadataRow
from fred_core.documents.document_store import DocumentSortField, SortOrder
from fred_core.documents.document_structures import (
    DocumentMetadata,
    FileInfo,
    Identity,
    ProcessingStage,
    ProcessingStatus,
    SourceInfo,
    SourceType,
    Tagging,
)
from fred_core.documents.label_models import DocumentLabelRow
from fred_core.documents.postgres_document_store import PostgresDocumentMetadataStore
from fred_core.documents.tag_models import TagRow
from fred_core.models.base import Base

pytestmark = [pytest.mark.integration, pytest.mark.integration_postgres]

_PG_DSN_ENV = "FRED_PG_DSN"
_DEFAULT_DSN = "postgresql+asyncpg://fred:Azerty123_@localhost:5432/fred"  # pragma: allowlist secret


@pytest_asyncio.fixture
async def pg_store() -> AsyncIterator[PostgresDocumentMetadataStore]:
    dsn = os.environ.get(_PG_DSN_ENV, _DEFAULT_DSN)
    schema = f"fred_core_itest_{uuid.uuid4().hex[:8]}"

    admin = create_async_engine(dsn)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    await admin.dispose()

    # `search_path` scopes the store's unqualified `UPDATE metadata` to this
    # test's own schema -- the SQL hardcodes the table name, so isolation has
    # to come from the connection rather than from a table prefix.
    engine = create_async_engine(
        dsn, connect_args={"server_settings": {"search_path": schema}}
    )
    try:
        async with engine.begin() as conn:
            await conn.run_sync(
                Base.metadata.create_all,
                tables=[
                    Base.metadata.tables[TagRow.__tablename__],
                    Base.metadata.tables[DocumentMetadataRow.__tablename__],
                    Base.metadata.tables[DocumentLabelRow.__tablename__],
                ],
            )
            await conn.execute(
                insert(TagRow),
                [
                    {"tag_id": tag_id, "owner_id": "team-a", "type": "document"}
                    for tag_id in ("tag-a", "folder-a", "folder-b")
                ],
            )
        yield PostgresDocumentMetadataStore(engine)
    finally:
        await engine.dispose()
        admin = create_async_engine(dsn)
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin.dispose()


def _doc(uid: str) -> DocumentMetadata:
    return DocumentMetadata(
        tags=Tagging(tag_ids=["tag-a"]),
        identity=Identity(document_name=f"{uid}.pdf", document_uid=uid, title=uid),
        source=SourceInfo(
            source_type=SourceType.PUSH, source_tag="fred", pull_location=None
        ),
    )


@pytest.mark.asyncio
async def test_touch_label_mutation_audit_fields_runs_on_postgres(
    pg_store: PostgresDocumentMetadataStore,
) -> None:
    """The regression itself: this statement used to fail at prepare time."""
    await pg_store.save_metadata(_doc("doc-1"))
    modified = datetime(2026, 8, 13, 13, 28, 55, tzinfo=timezone.utc)

    await pg_store.touch_label_mutation_audit_fields(
        "doc-1", modified=modified, modified_by="user-1"
    )

    after = await pg_store.get_metadata_by_uid("doc-1")
    assert after is not None
    assert after.identity.last_modified_by == "user-1"
    assert after.identity.modified == modified


@pytest.mark.asyncio
async def test_touch_label_mutation_audit_fields_preserves_the_rest_of_identity(
    pg_store: PostgresDocumentMetadataStore,
) -> None:
    """`jsonb_build_object` builds a whole `identity` object -- the merge must
    keep every key it does not set."""
    await pg_store.save_metadata(_doc("doc-1"))

    await pg_store.touch_label_mutation_audit_fields(
        "doc-1",
        modified=datetime(2026, 8, 13, tzinfo=timezone.utc),
        modified_by="user-1",
    )

    after = await pg_store.get_metadata_by_uid("doc-1")
    assert after is not None
    assert after.identity.document_name == "doc-1.pdf"
    assert after.identity.title == "doc-1"
    assert after.source.source_tag == "fred"


@pytest.mark.asyncio
async def test_bulk_mark_vector_done_runs_on_postgres(
    pg_store: PostgresDocumentMetadataStore,
) -> None:
    """The store's other raw-SQL write, covered here for the same reason."""
    md = _doc("doc-1")
    md.processing.errors[ProcessingStage.VECTORIZED] = "index mismatch"
    await pg_store.save_metadata(md)

    updated = await pg_store.bulk_mark_vector_done("fred", ["doc-1"])

    assert updated == ["doc-1"]
    after = await pg_store.get_metadata_by_uid("doc-1")
    assert after is not None
    assert after.processing.stages.get(ProcessingStage.VECTORIZED) == (
        ProcessingStatus.DONE
    )
    assert ProcessingStage.VECTORIZED not in after.processing.errors


def _sortable_doc(
    uid: str, name: str, *, day: int, size: int | None
) -> DocumentMetadata:
    return DocumentMetadata(
        identity=Identity(document_name=name, document_uid=uid, title=f"title-{uid}"),
        source=SourceInfo(
            source_type=SourceType.PUSH,
            source_tag="fred",
            pull_location=None,
            date_added_to_kb=datetime(2026, 1, day, tzinfo=timezone.utc),
        ),
        file=FileInfo(file_size_bytes=size),
        tags=Tagging(tag_ids=["tag-a"]),
    )


async def _seed_sortable(pg_store: PostgresDocumentMetadataStore) -> None:
    await pg_store.save_metadata(_sortable_doc("d1", "Zebra.pdf", day=3, size=100))
    await pg_store.save_metadata(_sortable_doc("d2", "annexe.pdf", day=1, size=1000))
    await pg_store.save_metadata(_sortable_doc("d3", "Beta.pdf", day=2, size=20))


async def _browse_names(
    pg_store: PostgresDocumentMetadataStore,
    sort_by: DocumentSortField,
    sort_order: SortOrder,
) -> list[str]:
    docs, _ = await pg_store.browse_metadata_in_tag(
        "tag-a", sort_by=sort_by, sort_order=sort_order
    )
    return [doc.identity.document_name for doc in docs]


@pytest.mark.asyncio
async def test_browse_sort_by_name_runs_on_postgres(
    pg_store: PostgresDocumentMetadataStore,
) -> None:
    """The ORDER BY reaches into the JSONB `doc` blob for the displayed name.
    SQLite takes the Python branch and never compiles this, so a wrong path or
    a missing `.astext` would only ever fail here."""
    await _seed_sortable(pg_store)

    assert await _browse_names(pg_store, "name", "asc") == [
        "annexe.pdf",
        "Beta.pdf",
        "Zebra.pdf",
    ]


@pytest.mark.asyncio
async def test_browse_sort_by_size_casts_out_of_jsonb_on_postgres(
    pg_store: PostgresDocumentMetadataStore,
) -> None:
    """Without the BIGINT cast this compares text: 1000 would file between 100
    and 20."""
    await _seed_sortable(pg_store)

    assert await _browse_names(pg_store, "size", "asc") == [
        "Beta.pdf",
        "Zebra.pdf",
        "annexe.pdf",
    ]


@pytest.mark.asyncio
async def test_browse_sort_by_created_runs_on_postgres(
    pg_store: PostgresDocumentMetadataStore,
) -> None:
    await _seed_sortable(pg_store)

    assert await _browse_names(pg_store, "created", "desc") == [
        "Zebra.pdf",
        "Beta.pdf",
        "annexe.pdf",
    ]


@pytest.mark.asyncio
async def test_browse_pages_a_tied_sort_without_repeating_on_postgres(
    pg_store: PostgresDocumentMetadataStore,
) -> None:
    """The uid tie-break, executed: three documents sharing a name must page
    as a total order, not in whatever sequence the planner returns."""
    for uid in ["c", "a", "b"]:
        await pg_store.save_metadata(_sortable_doc(uid, "same.pdf", day=1, size=10))

    seen: list[str] = []
    for offset in (0, 2):
        docs, _ = await pg_store.browse_metadata_in_tag(
            "tag-a", offset=offset, limit=2, sort_by="name", sort_order="asc"
        )
        seen.extend(doc.identity.document_uid for doc in docs)

    assert seen == ["a", "b", "c"]


def _named(uid: str, name: str, tag_ids: list[str]) -> DocumentMetadata:
    doc = _doc(uid)
    doc.identity.document_name = name
    doc.tags = Tagging(tag_ids=tag_ids)
    return doc


@pytest.mark.asyncio
async def test_uids_by_name_finds_only_names_in_that_tag(
    pg_store: PostgresDocumentMetadataStore,
) -> None:
    await pg_store.save_metadata(_named("d1", "report.pdf", ["folder-a"]))
    await pg_store.save_metadata(_named("d2", "notes.md", ["folder-a"]))
    await pg_store.save_metadata(_named("d3", "report.pdf", ["folder-b"]))

    found = await pg_store.document_uids_by_name_in_tag(
        "folder-a", ["report.pdf", "absent.pdf"]
    )

    assert found == {"report.pdf": ["d1"]}


@pytest.mark.asyncio
async def test_uids_by_name_reports_every_document_sharing_a_name(
    pg_store: PostgresDocumentMetadataStore,
) -> None:
    # A folder can already hold a base document and its alternate version under
    # the same display name, so a name does not identify a single document.
    await pg_store.save_metadata(_named("base", "report.pdf", ["folder-a"]))
    await pg_store.save_metadata(_named("alternate", "report.pdf", ["folder-a"]))

    found = await pg_store.document_uids_by_name_in_tag("folder-a", ["report.pdf"])

    assert sorted(found["report.pdf"]) == ["alternate", "base"]


@pytest.mark.asyncio
async def test_uids_by_name_with_no_names_touches_nothing(
    pg_store: PostgresDocumentMetadataStore,
) -> None:
    await pg_store.save_metadata(_named("d1", "report.pdf", ["folder-a"]))

    assert await pg_store.document_uids_by_name_in_tag("folder-a", []) == {}


@pytest.mark.asyncio
async def test_uids_by_name_uses_the_document_name_index(
    pg_store: PostgresDocumentMetadataStore,
) -> None:
    """The point of the query is that it is answered by index, not by a scan.

    Without the index this still returns the right answer, so only the plan can
    tell the two apart. It explains the statement the store itself builds —
    explaining a hand-written equivalent proves the index is matchable by THAT
    expression and nothing about the one that actually runs, which is how a
    query that could never use this index shipped once already.

    It also pins the index to the model: it is declared in `__table_args__`
    because an expression index has no column to hang off, and a module-level
    declaration would silently never reach the table.
    """
    from sqlalchemy import text as _text

    await pg_store.save_metadata(_named("d1", "report.pdf", ["folder-a"]))
    statement = pg_store._uids_by_name_statement(  # pyright: ignore[reportPrivateUsage]
        "folder-a", ["report.pdf"]
    )
    # Compiled without literal_binds and handed to the driver with its own
    # parameters: that is the form production actually sends, casts included.
    async with pg_store._sessions() as s:  # pyright: ignore[reportPrivateUsage]
        # With one row either index is equally selective. A populated folder
        # makes the name index useful and avoids an arbitrary planner tie.
        for index in range(1000):
            await pg_store.save_metadata(
                _named(f"other-{index}", f"other-{index}.pdf", ["folder-a"]),
                session=s,
            )
        await s.flush()
        await s.execute(_text("ANALYZE metadata"))
        connection = await s.connection()
        compiled = statement.compile(
            dialect=connection.dialect, compile_kwargs={"render_postcompile": True}
        )
        await s.execute(_text("SET enable_seqscan = off"))
        # The hostile case: a generic plan does not fold bind parameters, so an
        # index expression built out of them stops matching. Only a literal one
        # survives this.
        await s.execute(_text("SET plan_cache_mode = force_generic_plan"))
        # asyncpg is positional; positiontup is the order the placeholders take.
        result = await connection.exec_driver_sql(
            f"EXPLAIN {compiled}",
            tuple(compiled.params[key] for key in compiled.positiontup or ()),
        )
        plan = [row[0] for row in result]

    assert any("idx_metadata_document_name" in line for line in plan), plan


@pytest.mark.asyncio
async def test_folder_path_lookup_uses_the_unique_path_index(
    pg_store: PostgresDocumentMetadataStore,
) -> None:
    from sqlalchemy import select

    from fred_core.documents.tag_models import tag_full_path_expression

    async with pg_store._sessions() as session:
        await session.execute(
            insert(TagRow),
            [
                {
                    "tag_id": f"indexed-{i}",
                    "owner_id": "team-a",
                    "name": f"Folder-{i}",
                    "type": "document",
                }
                for i in range(1000)
            ],
        )
        await session.execute(text("ANALYZE tag"))
        await session.execute(text("SET plan_cache_mode = force_generic_plan"))
        statement = select(TagRow.tag_id).where(
            TagRow.owner_id == "team-a", tag_full_path_expression() == "Folder-17"
        )
        assert (await session.execute(statement)).scalar_one() == "indexed-17"
        connection = await session.connection()
        compiled = statement.compile(dialect=connection.dialect)
        plan = [
            row[0]
            for row in await connection.exec_driver_sql(
                f"EXPLAIN {compiled}",
                tuple(compiled.params[key] for key in compiled.positiontup or ()),
            )
        ]
    assert any("uq_tag_owner_full_path" in line for line in plan), plan
    assert any("Index Cond" in line and "COALESCE" in line for line in plan), plan
