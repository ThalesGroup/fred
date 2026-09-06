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

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base, utcnow


class CorpusRow(Base):
    """ORM model for the ``corpus`` table.

    Stores DB-backed corpus instance records — a team's instantiation of an
    enabled ``CorpusType`` (docs/swift/rfc/INDEXED-CORPUS-RFC.md §2/§4/§6).
    Never populated from deployment YAML — instance creation is operational
    data, same distinction as ``agent_instance`` vs. capability/app
    deployment config.
    """

    __tablename__ = "corpus"

    corpus_id: Mapped[str] = mapped_column(String, primary_key=True)
    corpus_type_id: Mapped[str] = mapped_column(String, nullable=False)
    team_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    tag_ids_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
        comment="JSON-serialized list[str] — CorpusScope.tag_ids",
    )
    connector_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
