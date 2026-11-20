# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""PostgreSQL upgrade and rollback of temporary preparation ownership."""

import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError


def _migration(filename: str):
    path = Path(__file__).parents[1] / "alembic/versions" / filename
    spec = importlib.util.spec_from_file_location(filename.removesuffix(".py"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.integration
@pytest.mark.integration_postgres
def test_draft_owner_migration_upgrades_and_rolls_back_without_affecting_existing_rows():
    url = os.environ.get("FRED_CAP_PREP_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set FRED_CAP_PREP_TEST_POSTGRES_URL for PostgreSQL verification")
    engine = sa.create_engine(url)
    schema = f"cap_prep_drafts_{uuid4().hex}"
    base = _migration("52344270c256_add_capability_preparation_state.py")
    drafts = _migration("8c9e1b472d35_add_capability_preparation_drafts.py")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            connection.exec_driver_sql(f'SET search_path TO "{schema}"')
            with Operations.context(MigrationContext.configure(connection)):
                base.upgrade()
                drafts.upgrade()
            assets = sa.Table(
                "capability_asset", sa.MetaData(), autoload_with=connection
            )
            base_asset = dict(
                owner_id="owner",
                runtime_id="runtime",
                capability_id="ppt_builder",
                slot_key="template",
                sha256="a" * 64,
                filename="deck.pptx",
                content_type="application/octet-stream",
                size=1,
                state="stored",
                created_at=sa.func.now(),
            )
            connection.execute(
                assets.insert().values(
                    **base_asset,
                    id=str(uuid4()),
                    owner_kind="agent",
                    team_id="team",
                    object_key=str(uuid4()),
                )
            )
            connection.execute(
                assets.insert().values(
                    **base_asset,
                    id=str(uuid4()),
                    owner_kind="draft",
                    team_id="team",
                    object_key=str(uuid4()),
                )
            )
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    assets.insert().values(
                        **base_asset,
                        id=str(uuid4()),
                        owner_kind="draft",
                        team_id=None,
                        object_key=str(uuid4()),
                    )
                )
            connection.execute(assets.delete().where(assets.c.owner_kind == "draft"))
            with Operations.context(MigrationContext.configure(connection)):
                drafts.downgrade()
            assert (
                connection.scalar(sa.select(sa.func.count()).select_from(assets)) == 1
            )
            constraint = {
                item["name"]: item["sqltext"]
                for item in sa.inspect(connection).get_check_constraints(
                    "capability_asset"
                )
            }
            assert "'draft'" not in constraint["ck_cap_asset_owner"]
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        engine.dispose()
