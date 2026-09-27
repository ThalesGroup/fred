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

"""A document addressed by the key the system that wrote it chose.

The rule that makes a synchronized library converge — one document per (library,
source key) — is the database's, not a caller's. These tests hold it there, plus
the two properties the rest of the design rests on: the key is stored verbatim
whatever it contains, and a document that has no key is never matched by one.

Runs against SQLite, like the store's other tests.
"""

from __future__ import annotations

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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


async def _make_sqlite_engine(tmp_path: Path) -> AsyncEngine:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'source-key.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


def _doc(
    uid: str,
    *,
    library: str | None = None,
    key: str | None = None,
    version: str | None = None,
    title: str = "original",
) -> DocumentMetadata:
    return DocumentMetadata(
        identity=Identity(document_name=f"{uid}.md", document_uid=uid, title=title),
        source=SourceInfo(
            source_type=SourceType.PUSH,
            source_tag="uploads",
            pull_location=None,
            source_library_id=library,
            source_key=key,
            document_version=version,
        ),
    )


@pytest.mark.asyncio
async def test_a_key_is_stored_and_returned_exactly_as_given(tmp_path):
    """Including characters no filesystem would take: the key is a name, not a path."""
    awkward = "notes/../ç'est [drôle] ?&#.md"
    store = PostgresDocumentMetadataStore(await _make_sqlite_engine(tmp_path))
    await store.save_metadata(
        _doc("doc-1", library="lib-1", key=awkward, version="etag-9")
    )

    found = await store.get_metadata_by_source_key("lib-1", awkward)

    assert found is not None
    assert found.source.source_key == awkward
    assert found.source.document_version == "etag-9"


@pytest.mark.asyncio
async def test_a_document_needs_no_version(tmp_path):
    store = PostgresDocumentMetadataStore(await _make_sqlite_engine(tmp_path))
    await store.save_metadata(_doc("doc-1", library="lib-1", key="readme.md"))

    found = await store.get_metadata_by_source_key("lib-1", "readme.md")

    assert found is not None
    assert found.source.document_version is None


@pytest.mark.asyncio
async def test_two_libraries_hold_the_same_key_independently(tmp_path):
    store = PostgresDocumentMetadataStore(await _make_sqlite_engine(tmp_path))
    await store.save_metadata(
        _doc("doc-a", library="lib-1", key="readme.md", title="one")
    )
    await store.save_metadata(
        _doc("doc-b", library="lib-2", key="readme.md", title="two")
    )

    await store.save_metadata(
        _doc("doc-a", library="lib-1", key="readme.md", title="one, edited")
    )

    first = await store.get_metadata_by_source_key("lib-1", "readme.md")
    second = await store.get_metadata_by_source_key("lib-2", "readme.md")
    assert first is not None and first.identity.title == "one, edited"
    assert second is not None and second.identity.title == "two"


@pytest.mark.asyncio
async def test_one_document_per_key_is_the_database_s_rule(tmp_path):
    """A second document claiming a key the library already holds is refused.

    The service resolves a write by looking the pair up, so it normally reuses
    the document already there; this is what stops two of them racing that
    lookup from both winning.
    """
    store = PostgresDocumentMetadataStore(await _make_sqlite_engine(tmp_path))
    await store.save_metadata(_doc("doc-a", library="lib-1", key="readme.md"))

    with pytest.raises(IntegrityError):
        await store.save_metadata(_doc("doc-b", library="lib-1", key="readme.md"))


@pytest.mark.asyncio
async def test_a_document_with_no_key_is_never_matched_by_one(tmp_path):
    """Someone's upload never becomes a synchronized document by resembling one."""
    store = PostgresDocumentMetadataStore(await _make_sqlite_engine(tmp_path))
    await store.save_metadata(_doc("uploaded", title="readme.md"))
    await store.save_metadata(_doc("other-upload", title="readme.md"))

    assert await store.get_metadata_by_source_key("lib-1", "readme.md") is None
    # Two keyless documents coexist: NULLs do not collide under the unique index.
    assert await store.get_metadata_by_uid("uploaded") is not None
    assert await store.get_metadata_by_uid("other-upload") is not None


@pytest.mark.asyncio
async def test_updating_a_document_carries_its_key_forward(tmp_path):
    """`update_metadata` writes the pair too, or an in-flight write would drop it."""
    store = PostgresDocumentMetadataStore(await _make_sqlite_engine(tmp_path))
    await store.save_metadata(_doc("doc-1", library="lib-1", key="readme.md"))

    assert (
        await store.update_metadata(
            _doc("doc-1", library="lib-1", key="readme.md", version="etag-2")
        )
        is True
    )

    found = await store.get_metadata_by_source_key("lib-1", "readme.md")
    assert found is not None
    assert found.identity.document_uid == "doc-1"
    assert found.source.document_version == "etag-2"


@pytest.mark.asyncio
async def test_a_library_lists_its_keyed_documents_in_key_order_and_no_others(tmp_path):
    """A keyless upload and another library's same key are both outside the page."""
    store = PostgresDocumentMetadataStore(await _make_sqlite_engine(tmp_path))
    await store.save_metadata(_doc("doc-b", library="lib-1", key="b.md", version="2"))
    await store.save_metadata(_doc("doc-a", library="lib-1", key="a.md", version="1"))
    await store.save_metadata(_doc("elsewhere", library="lib-2", key="a.md"))
    await store.save_metadata(_doc("uploaded", title="a.md"))

    page = await store.list_by_source_library("lib-1", limit=10)
    first = await store.list_by_source_library("lib-1", limit=1)

    assert [
        (d.identity.document_uid, d.source.source_key, d.source.document_version)
        for d in page
    ] == [("doc-a", "a.md", "1"), ("doc-b", "b.md", "2")]
    assert [d.identity.document_uid for d in first] == ["doc-a"]
