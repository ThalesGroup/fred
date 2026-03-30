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

from fred_core.models.base import JsonColumn, TimestampColumn
from sqlalchemy import Float, String
from sqlalchemy.orm import Mapped, mapped_column

from agentic_backend.models.base import Base


class AgentTaskRow(Base):
    """ORM model for the ``tasks`` table."""

    __tablename__ = "tasks"

    task_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    target_agent: Mapped[str] = mapped_column(String, index=True, nullable=False)
    request_text: Mapped[str] = mapped_column(String, nullable=False)
    workflow_id: Mapped[str] = mapped_column(
        String, unique=True, index=True, nullable=False
    )
    run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TimestampColumn, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TimestampColumn, nullable=False)
    context_json: Mapped[dict] = mapped_column(JsonColumn, nullable=False)
    parameters_json: Mapped[dict] = mapped_column(JsonColumn, nullable=False)
    last_message: Mapped[str | None] = mapped_column(String, nullable=True)
    percent_complete: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    blocked_json: Mapped[dict | None] = mapped_column(JsonColumn, nullable=True)
    artifacts_json: Mapped[list | None] = mapped_column(JsonColumn, nullable=True)
    error_json: Mapped[dict | None] = mapped_column(JsonColumn, nullable=True)
