# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Check the generic preparation schema and its revision fences."""

import importlib.util
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration():
    path = (
        Path(__file__).parents[1]
        / "alembic/versions/52344270c256_add_capability_preparation_state.py"
    )
    spec = importlib.util.spec_from_file_location(
        "capability_preparation_migration", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(
    params=[
        "sqlite",
        pytest.param(
            "postgresql",
            marks=[pytest.mark.integration, pytest.mark.integration_postgres],
        ),
    ]
)
def database(request):
    schema = None
    if request.param == "postgresql":
        url = os.environ.get("FRED_CAP_PREP_TEST_POSTGRES_URL")
        if not url:
            pytest.skip(
                "Set FRED_CAP_PREP_TEST_POSTGRES_URL for PostgreSQL verification"
            )
        schema = f"cap_prep_test_{uuid4().hex}"
        engine = sa.create_engine(url)
        with engine.begin() as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    else:
        engine = sa.create_engine("sqlite://")
    try:
        yield engine, schema
    finally:
        if schema is not None:
            with engine.begin() as connection:
                connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        engine.dispose()


def _run(engine, schema, operation):
    with engine.begin() as connection:
        if schema:
            connection.exec_driver_sql(f'SET search_path TO "{schema}"')
        with Operations.context(MigrationContext.configure(connection)):
            getattr(_migration(), operation)()


def _tables(engine, schema):
    with engine.connect() as connection:
        if schema:
            connection.exec_driver_sql(f'SET search_path TO "{schema}"')
        return set(sa.inspect(connection).get_table_names())


def _preparation(owner_id: str, revision: str, *, current: bool) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    return {
        "id": str(uuid4()),
        "owner_kind": "agent",
        "owner_id": owner_id,
        "team_id": "team-1",
        "runtime_id": "fred-agents",
        "capability_id": "test_cap",
        "input_revision": revision,
        "rules_version": "1",
        "config_json": {},
        "gates_readiness": True,
        "is_current": current,
        "state": "pending",
        "attempts": 0,
        "max_attempts": 3,
        "deadline_at": now,
        "workflow_id": f"prepare-{uuid4()}",
        "task_queue": "fred-agents-preparation",
        "delivery_due_at": now,
        "created_at": now,
        "updated_at": now,
    }


def test_upgrade_downgrade_and_revision_constraints(database):
    engine, schema = database
    _run(engine, schema, "upgrade")
    assert _tables(engine, schema) == {
        "capability_asset",
        "capability_preparation",
        "capability_preparation_asset",
    }
    with engine.begin() as connection:
        if schema:
            connection.exec_driver_sql(f'SET search_path TO "{schema}"')
        table = sa.Table(
            "capability_preparation", sa.MetaData(), autoload_with=connection
        )
        first = _preparation("agent-1", "revision-1", current=True)
        connection.execute(table.insert().values(**first))

        with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
            connection.execute(
                table.insert().values(
                    **_preparation("agent-1", "revision-1", current=False)
                )
            )
        with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
            connection.execute(
                table.insert().values(
                    **_preparation("agent-1", "revision-2", current=True)
                )
            )
        connection.execute(
            table.update().where(table.c.id == first["id"]).values(is_current=False)
        )
        second = _preparation("agent-1", "revision-2", current=True)
        connection.execute(table.insert().values(**second))
        with pytest.raises(sa.exc.IntegrityError), connection.begin_nested():
            connection.execute(
                table.update()
                .where(table.c.id == second["id"])
                .values(state="obsolete")
            )

    _run(engine, schema, "downgrade")
    assert _tables(engine, schema) == set()
