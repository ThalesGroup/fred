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

from __future__ import annotations

import functools
from typing import cast

from alembic import context
from fred_core.history.history_models import SessionHistoryRow  # noqa: F401
from fred_core.sql import make_alembic_env
from fred_core.sql.alembic_env import _build_url
from sqlalchemy import Column, Computed, ForeignKey, Index, MetaData, Table, Uuid
from sqlalchemy.ext.asyncio import create_async_engine

from fred_runtime.app.config_loader import load_agent_pod_config
from fred_runtime.app.web_research_activity import (
    WebResearchActivityRow,
)
from fred_runtime.migrations import configure_migration_logging

# Alembic Config object — provides access to values in alembic.ini.
config = context.config

# Run through the alembic CLI, not the `migrate` command that already configured it.
if config.config_file_name is not None:
    configure_migration_logging()

# Build a MetaData scoped to only the tables fred-runtime owns.
# SessionHistoryRow shares Base with other backends (users, session, teammetadata),
# so we must not pass Base.metadata directly — that would make alembic check
# report drift for tables managed by control-plane-backend.
_runtime_metadata = MetaData()
cast(Table, SessionHistoryRow.__table__).to_metadata(_runtime_metadata)
cast(Table, WebResearchActivityRow.__table__).to_metadata(_runtime_metadata)


# One configuration read per migration run, however often Alembic needs the URL.
@functools.cache
def _postgres_config():
    return load_agent_pod_config().storage.postgres


if _build_url(_postgres_config).startswith("postgresql"):
    from fred_runtime.runtime_support.session_fence import _fences, _writes
    from fred_runtime.runtime_support.sql_checkpointer import FredSqlCheckpointer

    # Metadata construction never connects. PostgreSQL checkpoint DDL now belongs
    # to this Alembic tree; SQLite still initializes its standalone tables.
    checkpoint = FredSqlCheckpointer(create_async_engine("postgresql+asyncpg://"))
    for table in checkpoint._metadata.tables.values():
        table.to_metadata(_runtime_metadata)
    Table(
        "session_metadata",
        _runtime_metadata,
        Column("session_id", Uuid, primary_key=True),
        schema="control_plane",
    )
    for name in (
        "session_history",
        *checkpoint._metadata.tables,
    ):
        table = _runtime_metadata.tables[name]
        source = (
            "split_part(thread_id, ':', 1)" if name.startswith("v2_") else "session_id"
        )
        table.append_column(
            Column(
                "conversation_id",
                Uuid,
                Computed(f"{source}::uuid", persisted=True),
                ForeignKey(
                    "control_plane.session_metadata.session_id",
                    ondelete="CASCADE",
                    name=f"{name}_conversation_fk",
                ),
                nullable=False,
            )
        )
        Index(f"{name}_conversation_idx", table.c.conversation_id)
    _fences.to_metadata(_runtime_metadata)
    _writes.to_metadata(_runtime_metadata)

run_migrations_offline, run_migrations_online = make_alembic_env(
    target_metadata=_runtime_metadata,
    get_postgres_config=_postgres_config,
    version_table="alembic_version_runtime",
    owned_tables=[
        table.name
        for table in _runtime_metadata.tables.values()
        if table.schema is None
    ],
)

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
