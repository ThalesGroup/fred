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

"""Offline regression tests for knowledge-flow's Alembic table ownership
(#2314, closing the #2313 defect).

What production taught us (2026-08-24, prism-swift-prod): the lifespan's
unfiltered ``create_all`` over the shared ``CoreBase`` created
``document_labels`` ahead of its migration, and the migration job then failed
forever on ``DuplicateTableError``. These tests pin the declarations that
prevent a recurrence: autogenerate/`alembic check` stay strictly inside the
declared owned set, and the startup guard covers every table this component
needs (mechanism behavior itself is covered by fred-core's
``test_schema_guard.py`` and ``test_alembic_env.py``).
"""

from __future__ import annotations

import sqlalchemy as sa
from fred_core.models.base import Base as CoreBase
from fred_core.sql.alembic_env import autogenerate_diffs

from knowledge_flow_backend.models.base import Base
from knowledge_flow_backend.models.table_ownership import (
    OWNED_TABLES,
    REQUIRED_TABLES,
    SHARED_CORE_TABLES,
)

# Tables migrated by the other trees sharing the database (control-plane,
# fred-runtime). Knowledge-flow must never own, create, or propose DDL for any
# of them.
_FOREIGN_TABLES = frozenset(
    {
        "users",
        "session",
        "session_metadata",
        "teammetadata",
        "session_history",
        "cp_task_run",
        "cp_task_event_log",
        "platformbootstrap",
    }
)


def test_owned_set_covers_kfb_tables_and_nothing_foreign() -> None:
    assert {"resource", "kf_task_run", "kf_task_event_log"} <= OWNED_TABLES
    assert SHARED_CORE_TABLES == {"tag", "metadata", "document_labels"}
    assert OWNED_TABLES.isdisjoint(_FOREIGN_TABLES)
    # Alembic-only, no ORM model: owning it would make autogenerate propose
    # its DROP (absent from every metadata).
    assert "sched_workflow_tasks" not in OWNED_TABLES


def test_required_set_adds_the_foreign_tables_kfb_reads() -> None:
    """The startup guard checks what the component NEEDS, not what it
    migrates: `users` and `teammetadata` are control-plane-owned but queried
    by ingestion/metadata code — missing them at boot must fail fast, not
    surface as UndefinedTableError mid-request."""
    assert OWNED_TABLES <= REQUIRED_TABLES
    assert {"users", "teammetadata"} <= REQUIRED_TABLES
    # Needed-but-foreign is not owned: the Alembic filter must stay strict.
    assert REQUIRED_TABLES - OWNED_TABLES == {"users", "teammetadata"}


def test_autogenerate_on_migrated_database_proposes_nothing() -> None:
    """The #2314 acceptance shape: against a database holding exactly the
    owned tables, autogenerate yields an empty migration — in particular no
    CREATE for the foreign `CoreBase` tables (users, session_history, ...)
    that are registered on the shared metadata but absent from the DB."""
    engine = sa.create_engine("sqlite://")
    metas = [Base.metadata, CoreBase.metadata]
    with engine.connect() as connection:
        Base.metadata.create_all(connection)
        CoreBase.metadata.create_all(
            connection,
            tables=[CoreBase.metadata.tables[name] for name in sorted(SHARED_CORE_TABLES)],
        )
        diffs = autogenerate_diffs(connection, metas, OWNED_TABLES)

    assert diffs == []
