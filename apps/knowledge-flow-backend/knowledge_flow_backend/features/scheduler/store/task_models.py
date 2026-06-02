# Copyright Thales 2025
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

from datetime import datetime

from fred_core.models.base import TimestampColumn
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from knowledge_flow_backend.models.base import Base


class WorkflowTaskRow(Base):
    """ORM model for the ``sched_workflow_tasks`` table."""

    __tablename__ = "sched_workflow_tasks"

    workflow_id: Mapped[str] = mapped_column(String, primary_key=True)
    current_document_uid: Mapped[str | None] = mapped_column(String, nullable=True)
    current_filename: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TimestampColumn, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TimestampColumn, nullable=False)
