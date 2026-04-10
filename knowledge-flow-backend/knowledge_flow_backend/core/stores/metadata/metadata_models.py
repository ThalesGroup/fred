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
from sqlalchemy import Index, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from knowledge_flow_backend.models.base import Base

# ARRAY(String) on PostgreSQL, plain JSON on SQLite (SQLite has no native array type).
TagIdsColumn = ARRAY(String).with_variant(JSON(), "sqlite")


class MetadataRow(Base):
    """ORM model for the ``metadata`` table."""

    __tablename__ = "metadata"

    document_uid: Mapped[str] = mapped_column(String, primary_key=True)
    source_tag: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    date_added_to_kb: Mapped[datetime | None] = mapped_column(TimestampColumn, nullable=True)
    tag_ids: Mapped[list | None] = mapped_column(TagIdsColumn, nullable=True)
    doc: Mapped[dict | None] = mapped_column(JsonColumn, nullable=True)


# GIN index for fast array containment queries on PostgreSQL.
# Ignored on SQLite (no GIN support).
_tag_ids_gin_index = Index(
    "idx_metadata_tag_ids_gin",
    MetadataRow.tag_ids,
    postgresql_using="gin",
)
