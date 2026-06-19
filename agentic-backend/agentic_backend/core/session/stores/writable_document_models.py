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

from fred_core.sql.mixin import TimestampMixin
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from agentic_backend.models.base import Base


class WritableDocumentRow(Base, TimestampMixin):
    """ORM model for the ``writable_documents`` table.

    A session-scoped collaborative markdown document. ``TimestampMixin`` provides
    ``created_at`` / ``updated_at`` (the latter drives user-edit detection).
    """

    __tablename__ = "writable_documents"

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    document_id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[str] = mapped_column(String, nullable=False)
