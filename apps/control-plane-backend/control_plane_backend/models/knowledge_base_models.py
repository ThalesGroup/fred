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

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from control_plane_backend.models.base import Base, utcnow


class KnowledgeBasePrefixRow(Base):
    """Which client owns a naming prefix.

    One row per prefix, so a first claim collides in PostgreSQL rather than in
    application code: two pods claiming the same prefix at the same instant
    cannot both win, whatever they publish under it.
    """

    __tablename__ = "knowledge_base_prefixes"

    prefix: Mapped[str] = mapped_column(String(256), primary_key=True)
    client_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Confidential M2M client that claimed this prefix first. Every "
        "later publication under it is checked against this value.",
    )
    claimed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class KnowledgeBaseDefinitionRow(Base):
    """ORM model for the ``knowledge_base_definitions`` table.

    The whole record Fred holds about a definition: its image published it, and
    nothing in deployment configuration declares it.

    Identified by its contributed name — ``fred.samples.local-folder`` — which
    already carries its provenance, so nothing here splits a name into parts.
    Ownership is the prefix it belongs to, and the foreign key makes "a
    definition always sits under a claimed prefix" a database invariant rather
    than a rule someone has to remember.
    """

    __tablename__ = "knowledge_base_definitions"

    id: Mapped[str] = mapped_column(
        String(256),
        primary_key=True,
        comment="Contributed name, dotted, under a prefix its contributor owns.",
    )
    prefix: Mapped[str] = mapped_column(
        String(256),
        ForeignKey("knowledge_base_prefixes.prefix"),
        nullable=False,
        index=True,
    )
    version: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    configuration_fields_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
        comment="JSON-serialized FieldSpec list the pod declared. Fred renders "
        "the instance configuration form from it and never interprets a value.",
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
