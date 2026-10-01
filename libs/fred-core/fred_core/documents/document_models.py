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

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from fred_core.models.base import Base, JsonColumn, TimestampColumn


class DocumentMetadataRow(Base):
    """ORM model for the ``metadata`` table."""

    __tablename__ = "metadata"

    document_uid: Mapped[str] = mapped_column(String, primary_key=True)
    source_tag: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    date_added_to_kb: Mapped[datetime | None] = mapped_column(
        TimestampColumn, nullable=True
    )
    kind: Mapped[str] = mapped_column(
        String, nullable=False, default="corpus", server_default="corpus"
    )
    folder_id: Mapped[str | None] = mapped_column(
        ForeignKey("tag.tag_id"), nullable=True, index=True
    )

    __table_args__ = (
        CheckConstraint(
            "(kind = 'corpus' AND folder_id IS NOT NULL) OR (kind = 'attachment' AND folder_id IS NULL)",
            name="ck_metadata_kind_folder",
        ),
    )
    # Denormalized out of `doc` (like `source_tag`) because the pair
    # carries a uniqueness rule the database has to enforce, and is the key a
    # synchronizing caller addresses its documents by. Both NULL for every
    # document not written through that surface — and NULLs never collide, so
    # ordinary ingestion is unaffected by the unique index below.
    source_library_id: Mapped[str | None] = mapped_column(String, nullable=True)
    source_key: Mapped[str | None] = mapped_column(String, nullable=True)
    doc: Mapped[dict | None] = mapped_column(JsonColumn, nullable=True)


# One document per (library, source key): re-writing a key updates the document
# already there instead of adding a second. Also the index the lookup uses.
# codeql[py/unused-global-variable]
_source_key_unique_index = Index(
    "uq_metadata_source_library_key",
    DocumentMetadataRow.source_library_id,
    DocumentMetadataRow.source_key,
    unique=True,
)
