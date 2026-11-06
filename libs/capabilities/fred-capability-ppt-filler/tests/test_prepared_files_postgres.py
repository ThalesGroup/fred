# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""The fresh schema and the upload/retirement race on real PostgreSQL row locks.

FRED_TEST_POSTGRES_URL must name an isolated local admin database.
"""

import asyncio
import hashlib
import os
import runpy
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fred_capability_ppt_filler.builder import analysis_job as jobs
from fred_capability_ppt_filler.builder import preparation
from fred_capability_ppt_filler.builder.builtin import builtin_template
from fred_sdk.contracts.capability.preparation import (
    PreparationContext,
    PreparationWork,
)
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.integration_postgres,
    pytest.mark.asyncio,
]
CONTENT = b"unused: the analysis is replaced by a stub"
VERSIONS = Path(jobs.__file__).resolve().parent / "ppt_builder_migrations" / "versions"


def _migrate(connection) -> None:
    with Operations.context(MigrationContext.configure(connection)):
        for migration in sorted(VERSIONS.glob("r*.py")):
            runpy.run_path(str(migration))["upgrade"]()


@pytest_asyncio.fixture
async def database() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    url = os.environ.get("FRED_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("FRED_TEST_POSTGRES_URL is required")
    admin = create_async_engine(url, isolation_level="AUTOCOMMIT")
    name = f"prepared_files_{uuid4().hex}"
    async with admin.connect() as connection:
        await connection.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_async_engine(make_url(url).set(database=name))
    async with engine.begin() as connection:
        await connection.execute(text("CREATE SCHEMA control_plane"))
        await connection.execute(
            text(
                "CREATE TABLE control_plane.session_metadata (session_id uuid PRIMARY KEY)"
            )
        )
        await connection.run_sync(_migrate)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()
    async with admin.connect() as connection:
        await connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
    await admin.dispose()


def _context(maker) -> PreparationContext:
    return PreparationContext(
        work=PreparationWork(
            preparation_id=uuid4(),
            installation_id=uuid4(),
            runtime_id="pod-a",
            capability_id="ppt_builder",
            space_id=uuid4(),
            agent_instance_id=uuid4(),
            configuration_revision=1,
            file_id=uuid4(),
            sha256=hashlib.sha256(CONTENT).hexdigest(),
            filename="model.pptx",
            size=len(CONTENT),
            config={},
            state="pending",
        ),
        database=maker.kw["bind"],
        content=CONTENT,
    )


async def test_the_fresh_schema_has_no_binary_and_protects_publication(database):
    def columns(connection):
        return {
            column["name"]
            for column in inspect(connection).get_columns("cap_ppt_builder_analysis")
        }

    async with database.kw["bind"].connect() as connection:
        names = await connection.run_sync(columns)
    assert {"template_digest", "patterns_digest", "pending_writes"} <= names
    assert not {"template_pptx", "patterns_pdf"} & names

    ctx = _context(database)
    store = await preparation._reserve(ctx)
    identity = preparation.analysis_identity(ctx)
    with pytest.raises(IntegrityError, match="published_check"):
        await store._update(identity, status="succeeded")
    with pytest.raises(IntegrityError, match="pending_writes_check"):
        await store._update(identity, pending_writes=-1)


async def test_no_retirement_order_lets_a_write_survive_confirmed_erasure(
    database, objects, monkeypatch
):
    async def analyse(content, port, key):
        return builtin_template()[1], b"%PDF"

    monkeypatch.setattr(jobs, "_analyse", analyse)
    monkeypatch.setattr(preparation, "sanitize_template", lambda content: content)

    async def slow_put(path: str) -> None:
        await asyncio.sleep(0.005)

    objects.before_write = slow_put

    async def race(delay: float) -> None:
        ctx = _context(database)

        async def cleanup_until_confirmed() -> None:
            # As the worker's cleanup does, concurrently with the running attempt.
            await asyncio.sleep(delay)
            while True:
                try:
                    return await preparation.retire(ctx)
                except jobs.PreparationWritesPending:
                    await asyncio.sleep(0.002)

        results = await asyncio.gather(
            preparation.prepare(ctx), cleanup_until_confirmed(), return_exceptions=True
        )
        assert results[1] is None
        # Nothing may land after the confirmation: the attempt has really ended here.
        directory = str(ctx.work.preparation_id)
        assert not [key for key in objects.files if key.startswith(f"{directory}/")]
        store = jobs.SqlAnalysisStore(database)
        record = await store.get(preparation.analysis_identity(ctx))
        assert record is not None and record.status == "retired"

    # Before, around and after the first write, with real overlapping row locks.
    await asyncio.gather(*(race(i * 0.002) for i in range(30)))
    assert not jobs._uploads
