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

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from fred_core.models.base import Base


class DocumentLabelRow(Base):
    """ORM model for the ``document_labels`` table: one row per (document,
    descriptive label) assignment. Not a vocabulary — a label with no
    document rows referencing it simply doesn't exist anywhere; there is no
    separate definitions table.

    The composite primary key is the idempotency mechanism: a duplicate
    assignment is rejected by the constraint itself (`INSERT ... ON CONFLICT
    DO NOTHING` in `PostgresDocumentMetadataStore.add_label`), not by a
    precomputed Python check that could itself race.
    """

    __tablename__ = "document_labels"

    document_uid: Mapped[str] = mapped_column(
        String,
        ForeignKey("metadata.document_uid", ondelete="CASCADE"),
        primary_key=True,
    )
    label: Mapped[str] = mapped_column(String, primary_key=True)


# Search index for exact-match label lookups ("documents carrying label X")
# and distinct-label listing, both scanning by label first.
# codeql[py/unused-global-variable]
_document_labels_search_index = Index(
    "idx_document_labels_label_document_uid",
    DocumentLabelRow.label,
    DocumentLabelRow.document_uid,
)
