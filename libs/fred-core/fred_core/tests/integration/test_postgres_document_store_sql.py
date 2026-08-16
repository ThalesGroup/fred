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
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from fred_core.documents.document_models import DocumentMetadataRow
from fred_core.documents.document_structures import (
    DocumentMetadata,
    Identity,
    ProcessingStage,
    ProcessingStatus,
    SourceInfo,
    SourceType,
)
from fred_core.documents.label_models import DocumentLabelRow
from fred_core.documents.postgres_document_store import PostgresDocumentMetadataStore
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
                    Base.metadata.tables[DocumentMetadataRow.__tablename__],
                    Base.metadata.tables[DocumentLabelRow.__tablename__],
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
