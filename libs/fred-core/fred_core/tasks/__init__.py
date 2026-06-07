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

from fred_core.tasks.bus import IEventBus, MemoryEventBus, PostgresEventBus
from fred_core.tasks.models import (
    ActivityContext,
    IngestionDetail,
    IngestionProcessingProfile,
    IngestionTaskEvent,
    StartIngestionParams,
    StartIngestionRequest,
    StartTaskRequest,
    StartTaskResponse,
    TaskEvent,
    TaskListResponse,
    TaskLogDetail,
    TaskLogEvent,
    TaskState,
    TaskSummary,
    TaskTarget,
)
from fred_core.tasks.orm_models import TaskEventLogRow, TaskRunRow
from fred_core.tasks.scheduler import IScheduler, MemoryScheduler, TemporalScheduler
from fred_core.tasks.service import TaskService
from fred_core.tasks.sse import HEARTBEAT_INTERVAL, with_heartbeat
from fred_core.tasks.store import TaskNotFoundError, TaskStore

__all__ = [
    # models
    "TaskState",
    "TaskTarget",
    "IngestionProcessingProfile",
    "TaskEvent",
    "IngestionTaskEvent",
    "TaskLogEvent",
    "IngestionDetail",
    "TaskLogDetail",
    "StartTaskRequest",
    "StartTaskResponse",
    "StartIngestionRequest",
    "StartIngestionParams",
    "TaskSummary",
    "TaskListResponse",
    "ActivityContext",
    # orm models
    "TaskRunRow",
    "TaskEventLogRow",
    # bus
    "IEventBus",
    "MemoryEventBus",
    "PostgresEventBus",
    # scheduler
    "IScheduler",
    "MemoryScheduler",
    "TemporalScheduler",
    # store
    "TaskNotFoundError",
    "TaskStore",
    # service
    "TaskService",
    # sse
    "HEARTBEAT_INTERVAL",
    "with_heartbeat",
]
