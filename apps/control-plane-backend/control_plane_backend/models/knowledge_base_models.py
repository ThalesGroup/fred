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


class KnowledgeBaseDefinitionRow(Base):
    """ORM model for the ``knowledge_base_definitions`` table.

    The whole record Fred holds about a definition: its image published it,
    and nothing in deployment configuration declares it.

    Identified by ``(provider_id, definition_id)``: a provider exposes several
    Knowledge Bases, and two providers may each expose one of the same name.
    ``client_id`` is bound to the PROVIDER by its first publication, so a
    workload owns its namespace and can never write into another's.
    """

    __tablename__ = "knowledge_base_definitions"

    provider_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    definition_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    client_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Confidential M2M client bound to this provider at its first "
        "publication. Every publication for this provider is checked against it.",
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
