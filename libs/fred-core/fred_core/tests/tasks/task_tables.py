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

"""A concrete task pair for fred-core's own tests (#2170).

`fred_core.tasks.orm_models` deliberately maps nothing: each backend declares
its own `cp_`/`kf_`-prefixed pair. fred-core's tests exercise `TaskStore` and
`TaskService` without either backend installed, so they need a pair of their
own — declared here once rather than in every test module.

Declared on a test-local `DeclarativeBase`, never on the shared `CoreBase` —
`fred_core.tests` ships in the wheel, and anything mapped on `CoreBase` is
created by knowledge-flow's unfiltered startup `create_all` and proposed by both
alembic trees' autogenerate. That is the exact hazard #2170 removes for the real
task tables; re-introducing it for a test fixture would be perverse. Same shape
as `test_table_isolation.py`.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase

from fred_core.tasks.orm_models import (
    TaskEventLogColumns,
    TaskRunColumns,
    TaskTables,
    task_event_log_table_args,
    task_run_table_args,
)


class Base(DeclarativeBase):
    """Isolated from `fred_core.models.base.Base` on purpose — see the module docstring."""


_RUN = "test_task_run"
_LOG = "test_task_event_log"


class TaskRunRow(TaskRunColumns, Base):
    __tablename__ = _RUN
    __table_args__ = task_run_table_args(_RUN)


class TaskEventLogRow(TaskEventLogColumns, Base):
    __tablename__ = _LOG
    __table_args__ = task_event_log_table_args(_LOG)


TASK_TABLES = TaskTables(run=TaskRunRow, event_log=TaskEventLogRow)
