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

"""Knowledge-flow's own task tables (#2170, TASK-EVENT-STREAM-RFC §2.6).

Declared on knowledge-flow's `Base`, not the shared `CoreBase`: these two tables
belong to this backend alone. control-plane owns the `cp_`-prefixed pair in the
same `fred` database (`control_plane_backend.models.task_models`). Before the
split both backends mapped one shared `task_run`, so each one's `GET /tasks`
returned the other's rows and the Activity page listed every task twice.

Column definitions live once, in `fred_core.tasks.orm_models` — only the names
differ between the two owners.
"""

from __future__ import annotations

from fred_core.tasks.orm_models import (
    TaskEventLogColumns,
    TaskRunColumns,
    TaskTables,
    task_event_log_table_args,
    task_run_table_args,
)

from knowledge_flow_backend.models.base import Base

TASK_RUN_TABLE = "kf_task_run"
TASK_EVENT_LOG_TABLE = "kf_task_event_log"


class KfTaskRunRow(TaskRunColumns, Base):
    __tablename__ = TASK_RUN_TABLE
    __table_args__ = task_run_table_args(TASK_RUN_TABLE)


class KfTaskEventLogRow(TaskEventLogColumns, Base):
    __tablename__ = TASK_EVENT_LOG_TABLE
    __table_args__ = task_event_log_table_args(TASK_EVENT_LOG_TABLE)


TASK_TABLES = TaskTables(run=KfTaskRunRow, event_log=KfTaskEventLogRow)
