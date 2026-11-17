# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Exercise schema initialization on an isolated schema in FRED_PG_DSN."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.schema import DropSchema

from fred_core.tests.sql.test_alembic_env import _migration_fixture

pytestmark = [pytest.mark.integration, pytest.mark.integration_postgres]


def test_fresh_schema_and_repeated_migration(tmp_path, monkeypatch):
    dsn = os.environ.get("FRED_PG_DSN")
    if not dsn:
        pytest.skip("Set FRED_PG_DSN to a local PostgreSQL test database")
    schema = f"alembic_test_{uuid4().hex}"
    monkeypatch.setenv("DATABASE_URL", dsn)
    monkeypatch.setenv("DATABASE_SCHEMA", schema)
    config = _migration_fixture(tmp_path, create_schema=True)

    async def state(*, cleanup=False):
        engine = create_async_engine(dsn)
        try:
            async with engine.begin() as connection:
                if cleanup:
                    await connection.execute(
                        DropSchema(schema, cascade=True, if_exists=True)
                    )
                    return None
                exists = await connection.scalar(
                    text("SELECT to_regnamespace(:schema)"), {"schema": schema}
                )
                if exists is None:
                    return None
                return await connection.run_sync(
                    lambda conn: inspect(conn).get_table_names(schema=schema)
                )
        finally:
            await engine.dispose()

    try:
        assert asyncio.run(state()) is None
        command.upgrade(config, "head")
        tables = asyncio.run(state())
        assert tables is not None
        assert set(tables) == {"alembic_version", "owned"}
        command.upgrade(config, "head")
        tables = asyncio.run(state())
        assert tables is not None
        assert set(tables) == {"alembic_version", "owned"}
    finally:
        asyncio.run(state(cleanup=True))
