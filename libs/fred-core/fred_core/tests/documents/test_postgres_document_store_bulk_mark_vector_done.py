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

"""`PostgresDocumentMetadataStore.bulk_mark_vector_done` -- the only write the
vector-metadata repair action (#2234, 3a) performs.

Runs against SQLite, which takes the store's Python-fallback branch (no
`jsonb`/`||`/`#>>` operators) -- the same branch every other JSON-manipulating
method in this store already falls back to for tests (see
`test_postgres_document_store_count_by_team.py`). IMPORTANT LIMITATION: this
means the actual PostgreSQL `jsonb_build_object`/`COALESCE`/`#>>` SQL text
(the part of the #2234 fix that specifically handles a document whose
`processing`/`stages` JSON key is missing) is exercised here only via its
Python-fallback *equivalent*, not the raw SQL itself -- there is no PostgreSQL
available in this environment to test that text directly. The SQL was
reviewed carefully (see the method's docstring) but is not executed by any
test in this repository; recommend verifying it directly against a real
PostgreSQL instance during manual testing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fred_core.documents.document_models import DocumentMetadataRow
from fred_core.documents.document_structures import (
    DocumentMetadata,
    Identity,
    ProcessingStage,
    ProcessingStatus,
    SourceInfo,
    SourceType,
)
from fred_core.documents.postgres_document_store import PostgresDocumentMetadataStore
from fred_core.models.base import Base
from fred_core.sql.async_session import make_session_factory
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine


async def _make_sqlite_engine(tmp_path: Path, filename: str) -> AsyncEngine:
    db_path = tmp_path / filename
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


def _doc(uid: str, source_tag: str = "fred") -> DocumentMetadata:
    return DocumentMetadata(
        identity=Identity(document_name=f"{uid}.pdf", document_uid=uid, title=uid),
        source=SourceInfo(
            source_type=SourceType.PUSH, source_tag=source_tag, pull_location=None
        ),
    )


async def _insert_raw_row(
    sessions: async_sessionmaker, *, document_uid: str, source_tag: str, doc: dict
) -> None:
    """Insert a row with a hand-crafted `doc` JSON blob, bypassing
    `DocumentMetadata`/`save_metadata` entirely -- the only way to construct a
    row whose `processing`/`stages`/`errors` keys are genuinely absent (going
    through the pydantic model always populates them via `Processing`'s
    `default_factory`)."""
    async with sessions() as s:
        async with s.begin():
            s.add(
                DocumentMetadataRow(
                    document_uid=document_uid,
                    source_tag=source_tag,
                    tag_ids=[],
                    doc=doc,
                )
            )


def _vector_stage(md: DocumentMetadata) -> ProcessingStatus | None:
    return md.processing.stages.get(ProcessingStage.VECTORIZED)


@pytest.mark.asyncio
async def test_bulk_mark_vector_done_sets_vector_done_and_clears_the_vector_error(
    tmp_path: Path,
) -> None:
    engine = await _make_sqlite_engine(tmp_path, "bulk_basic.sqlite3")
    store = PostgresDocumentMetadataStore(engine)
    md = _doc("doc-1")
    md.processing.errors[ProcessingStage.VECTORIZED] = "index mismatch"
    await store.save_metadata(md)

    updated = await store.bulk_mark_vector_done("fred", ["doc-1"])

    assert updated == ["doc-1"]
    result = await store.get_metadata_by_uid("doc-1")
    assert result is not None
    assert _vector_stage(result) == ProcessingStatus.DONE
    assert ProcessingStage.VECTORIZED not in result.processing.errors


@pytest.mark.asyncio
async def test_bulk_mark_vector_done_touches_only_the_two_allowed_json_paths(
    tmp_path: Path,
) -> None:
    """Everything else on the document -- identity, source, tags, other
    processing stages, other processing errors -- must survive byte-for-byte."""
    engine = await _make_sqlite_engine(tmp_path, "bulk_scope.sqlite3")
    store = PostgresDocumentMetadataStore(engine)
    md = _doc("doc-1")
    md.processing.stages[ProcessingStage.RAW_AVAILABLE] = ProcessingStatus.DONE
    md.processing.stages[ProcessingStage.PREVIEW_READY] = ProcessingStatus.IN_PROGRESS
    md.processing.errors[ProcessingStage.SQL_INDEXED] = "unrelated tabular failure"
    md.tags.tag_ids = ["tag-a", "tag-b"]
    before = await store.save_metadata(md) or md

    await store.bulk_mark_vector_done("fred", ["doc-1"])

    after = await store.get_metadata_by_uid("doc-1")
    assert after is not None
    assert after.identity == before.identity
    assert after.source == before.source
    assert after.tags.tag_ids == ["tag-a", "tag-b"]
    assert (
        after.processing.stages[ProcessingStage.RAW_AVAILABLE] == ProcessingStatus.DONE
    )
    assert (
        after.processing.stages[ProcessingStage.PREVIEW_READY]
        == ProcessingStatus.IN_PROGRESS
    )
    assert (
        after.processing.errors[ProcessingStage.SQL_INDEXED]
        == "unrelated tabular failure"
    )
    assert _vector_stage(after) == ProcessingStatus.DONE


@pytest.mark.asyncio
async def test_bulk_mark_vector_done_works_when_processing_is_entirely_absent(
    tmp_path: Path,
) -> None:
    """A row whose `doc` JSON has no `processing` key at all (e.g. a very old or
    hand-restored row) must not crash, and must end up with exactly
    `processing.stages.vector = done` -- proving `processing`/`stages` are
    created, not assumed present (the exact PostgreSQL `jsonb_set(...,
    create_missing=true)` pitfall this fix addresses -- see module docstring
    for the SQLite-vs-PostgreSQL coverage caveat)."""
    engine = await _make_sqlite_engine(tmp_path, "bulk_no_processing.sqlite3")
    sessions = make_session_factory(engine)
    store = PostgresDocumentMetadataStore(engine)
    raw_doc = {
        "identity": {
            "document_name": "doc-1.pdf",
            "document_uid": "doc-1",
            "title": "doc-1",
        },
        "source": {"source_type": "push", "source_tag": "fred"},
        # no "processing" key at all
    }
    await _insert_raw_row(
        sessions, document_uid="doc-1", source_tag="fred", doc=raw_doc
    )

    updated = await store.bulk_mark_vector_done("fred", ["doc-1"])

    assert updated == ["doc-1"]
    result = await store.get_metadata_by_uid("doc-1")
    assert result is not None
    assert _vector_stage(result) == ProcessingStatus.DONE


@pytest.mark.asyncio
async def test_bulk_mark_vector_done_works_when_stages_is_absent_but_processing_is_present(
    tmp_path: Path,
) -> None:
    engine = await _make_sqlite_engine(tmp_path, "bulk_no_stages.sqlite3")
    sessions = make_session_factory(engine)
    store = PostgresDocumentMetadataStore(engine)
    raw_doc = {
        "identity": {
            "document_name": "doc-1.pdf",
            "document_uid": "doc-1",
            "title": "doc-1",
        },
        "source": {"source_type": "push", "source_tag": "fred"},
        "processing": {},  # present, but no "stages"/"errors" keys
    }
    await _insert_raw_row(
        sessions, document_uid="doc-1", source_tag="fred", doc=raw_doc
    )

    updated = await store.bulk_mark_vector_done("fred", ["doc-1"])

    assert updated == ["doc-1"]
    result = await store.get_metadata_by_uid("doc-1")
    assert result is not None
    assert _vector_stage(result) == ProcessingStatus.DONE


@pytest.mark.asyncio
async def test_bulk_mark_vector_done_works_when_errors_is_absent(
    tmp_path: Path,
) -> None:
    engine = await _make_sqlite_engine(tmp_path, "bulk_no_errors.sqlite3")
    sessions = make_session_factory(engine)
    store = PostgresDocumentMetadataStore(engine)
    raw_doc = {
        "identity": {
            "document_name": "doc-1.pdf",
            "document_uid": "doc-1",
            "title": "doc-1",
        },
        "source": {"source_type": "push", "source_tag": "fred"},
        "processing": {"stages": {"raw": "done"}},  # no "errors" key
    }
    await _insert_raw_row(
        sessions, document_uid="doc-1", source_tag="fred", doc=raw_doc
    )

    updated = await store.bulk_mark_vector_done("fred", ["doc-1"])

    assert updated == ["doc-1"]
    result = await store.get_metadata_by_uid("doc-1")
    assert result is not None
    assert _vector_stage(result) == ProcessingStatus.DONE
    assert (
        result.processing.stages[ProcessingStage.RAW_AVAILABLE] == ProcessingStatus.DONE
    )


@pytest.mark.asyncio
async def test_bulk_mark_vector_done_rolls_back_everything_when_one_uid_is_absent(
    tmp_path: Path,
) -> None:
    """A document_uid absent from the table entirely (never existed, or a typo
    in the caller's scan result) must fail the WHOLE batch -- including the
    other, genuinely valid uids in the same call -- rather than silently
    repairing a partial set."""
    engine = await _make_sqlite_engine(tmp_path, "bulk_missing_uid.sqlite3")
    store = PostgresDocumentMetadataStore(engine)
    await store.save_metadata(_doc("doc-1"))

    with pytest.raises(RuntimeError, match="not found under source_tag"):
        await store.bulk_mark_vector_done("fred", ["doc-1", "doc-does-not-exist"])

    # doc-1 would have matched on its own -- it must still be untouched.
    result = await store.get_metadata_by_uid("doc-1")
    assert result is not None
    assert _vector_stage(result) != ProcessingStatus.DONE


@pytest.mark.asyncio
async def test_bulk_mark_vector_done_rolls_back_everything_when_a_uid_source_tag_no_longer_matches(
    tmp_path: Path,
) -> None:
    """A document whose `source_tag` changed between the caller's earlier scan
    and this write (e.g. re-tagged mid-repair) is out of scope -- and, same as
    the absent-uid case, must fail the whole batch rather than silently
    excluding just that one uid."""
    engine = await _make_sqlite_engine(tmp_path, "bulk_retagged.sqlite3")
    store = PostgresDocumentMetadataStore(engine)
    await store.save_metadata(_doc("doc-1", source_tag="fred"))
    await store.save_metadata(_doc("doc-2", source_tag="some-other-tag"))

    with pytest.raises(RuntimeError, match="not found under source_tag"):
        await store.bulk_mark_vector_done("fred", ["doc-1", "doc-2"])

    result = await store.get_metadata_by_uid("doc-1")
    assert result is not None
    assert _vector_stage(result) != ProcessingStatus.DONE


@pytest.mark.asyncio
async def test_bulk_mark_vector_done_retry_converges_to_the_same_final_state(
    tmp_path: Path,
) -> None:
    engine = await _make_sqlite_engine(tmp_path, "bulk_retry.sqlite3")
    store = PostgresDocumentMetadataStore(engine)
    await store.save_metadata(_doc("doc-1"))

    first = await store.bulk_mark_vector_done("fred", ["doc-1"])
    after_first = await store.get_metadata_by_uid("doc-1")
    assert after_first is not None

    second = await store.bulk_mark_vector_done("fred", ["doc-1"])
    after_second = await store.get_metadata_by_uid("doc-1")
    assert after_second is not None

    assert first == second == ["doc-1"]
    assert after_first.model_dump(mode="json") == after_second.model_dump(mode="json")
    assert _vector_stage(after_second) == ProcessingStatus.DONE


@pytest.mark.asyncio
async def test_bulk_mark_vector_done_returns_empty_list_and_touches_nothing_for_empty_input(
    tmp_path: Path,
) -> None:
    engine = await _make_sqlite_engine(tmp_path, "bulk_empty.sqlite3")
    store = PostgresDocumentMetadataStore(engine)
    await store.save_metadata(_doc("doc-1"))

    result = await store.bulk_mark_vector_done("fred", [])

    assert result == []
    after = await store.get_metadata_by_uid("doc-1")
    assert after is not None
    assert _vector_stage(after) != ProcessingStatus.DONE


@pytest.mark.asyncio
async def test_bulk_mark_vector_done_deduplicates_repeated_uids_in_the_input(
    tmp_path: Path,
) -> None:
    engine = await _make_sqlite_engine(tmp_path, "bulk_dedup.sqlite3")
    store = PostgresDocumentMetadataStore(engine)
    await store.save_metadata(_doc("doc-1"))

    updated = await store.bulk_mark_vector_done("fred", ["doc-1", "doc-1", "doc-1"])

    assert updated == ["doc-1"]
