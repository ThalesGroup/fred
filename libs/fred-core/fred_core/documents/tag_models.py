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

from datetime import datetime

from sqlalchemy import Index, String, func, literal_column
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.expression import Grouping

from fred_core.models.base import Base, JsonColumn, TimestampColumn


class TagRow(Base):
    """ORM model for the ``tag`` table — shared between knowledge-flow and the importer."""

    __tablename__ = "tag"

    tag_id: Mapped[str] = mapped_column(String, primary_key=True)
    deletion_task_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(TimestampColumn, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(
        TimestampColumn, index=True, nullable=True
    )
    owner_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    name: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    path: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    type: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    doc: Mapped[dict | None] = mapped_column(JsonColumn, nullable=True)


def tag_full_path_expression() -> ColumnElement[str]:
    """Use the indexed expression, including in generic PostgreSQL plans."""
    return (
        func.coalesce(
            func.nullif(TagRow.path, literal_column("''"), type_=String)
            + literal_column("'/'", String),
            literal_column("''"),
        )
        + TagRow.name
    )


# owner_id attaches this expression index to the mapped table.
_full_path_unique_index = Index(
    "uq_tag_owner_full_path",
    TagRow.owner_id,
    Grouping(tag_full_path_expression()),
    unique=True,
)
