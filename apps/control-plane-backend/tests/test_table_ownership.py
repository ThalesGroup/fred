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

"""Offline regression tests for control-plane's Alembic table ownership
(#2314).

The acceptance case from the issue, verbatim: running autogenerate in
control-plane against a database where knowledge-flow's ``tag`` /
``metadata`` are absent must yield an empty migration — not a second writer
creating tables another tree owns.
"""

from __future__ import annotations

import control_plane_backend.evaluations.models  # noqa: F401 — registers evaluation_* on Base, proving the exclusion below holds even when imported
import fred_core.documents.document_models  # noqa: F401 — registers tag/metadata on CoreBase, the foreign side this test proves is excluded
import sqlalchemy as sa
from control_plane_backend.models.base import Base
from control_plane_backend.models.table_ownership import (
    OWNED_TABLES,
    SHARED_CORE_TABLES,
)
from fred_core.models.base import Base as CoreBase
from fred_core.sql.alembic_env import autogenerate_diffs

# Tables migrated by the other trees sharing the database (knowledge-flow,
# fred-runtime) or living in another database entirely (fred-evaluation).
# Control-plane must never own or propose DDL for any of them.
_FOREIGN_TABLES = frozenset(
    {
        "tag",
        "metadata",
        "document_labels",
        "session_history",
        "resource",
        "kf_task_run",
        "kf_task_event_log",
        "sched_workflow_tasks",
        "evaluation_campaign",
        "evaluation_case",
        "evaluation_metric_result",
    }
)


def test_owned_set_covers_cp_tables_and_nothing_foreign() -> None:
    assert {"cp_task_run", "cp_task_event_log"} <= OWNED_TABLES
    assert SHARED_CORE_TABLES == {"users", "session", "teammetadata"}
    # Includes the evaluation_* tables: they sit on CP's own Base but are
    # migrated by the separate fred-evaluation tree — deriving ownership from
    # Base.metadata alone would claim them the moment their module is
    # imported (as this test module deliberately does).
    assert OWNED_TABLES.isdisjoint(_FOREIGN_TABLES)


def test_autogenerate_without_knowledge_flow_tables_yields_empty_migration() -> None:
    engine = sa.create_engine("sqlite://")
    metas = [Base.metadata, CoreBase.metadata]
    owned_app_tables = [
        table for name, table in Base.metadata.tables.items() if name in OWNED_TABLES
    ]
    with engine.connect() as connection:
        # A database holding exactly control-plane's owned tables — and none
        # of knowledge-flow's (`tag`/`metadata` deliberately absent).
        Base.metadata.create_all(connection, tables=owned_app_tables)
        CoreBase.metadata.create_all(
            connection,
            tables=[
                CoreBase.metadata.tables[name] for name in sorted(SHARED_CORE_TABLES)
            ],
        )
        diffs = autogenerate_diffs(connection, metas, OWNED_TABLES)

    assert diffs == []
