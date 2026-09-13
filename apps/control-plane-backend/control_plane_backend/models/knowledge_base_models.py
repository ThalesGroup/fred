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

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
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
    subject: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Service account the claiming client authenticates as (`sub`). "
        "The client is what a prefix is bound to; this is the only one of the "
        "two the authorization engine can be told to grant, so creating an "
        "instance reads it here instead of asking Keycloak's admin API which "
        "account backs a client. Nullable for prefixes claimed before it was "
        "recorded; the next publication fills it in.",
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


class KnowledgeBaseInstanceRow(Base):
    """ORM model for the ``knowledge_base_instances`` table.

    One synchronized folder: the library it fills, the definition that fills
    it, the team that owns both, and the cadence Fred runs it on. The library
    id is knowledge-flow's tag id — this row is what binds the two together,
    and deleting it is what ends the synchronization.

    A team may hold several instances of one definition, each with its own
    library and its own grant, so nothing here is unique per (team, definition).
    """

    __tablename__ = "knowledge_base_instances"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    definition_id: Mapped[str] = mapped_column(
        String(256),
        ForeignKey("knowledge_base_definitions.id"),
        nullable=False,
        index=True,
    )
    team_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    library_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        comment="knowledge-flow tag this instance fills. Unique: two instances "
        "sharing a library would each grant a different pod over it.",
    )
    library_name: Mapped[str] = mapped_column(String(255), nullable=False)
    cadence: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="How often Fred dispatches a run. One of the SDK's declared "
        "cadences — the vocabulary is the platform's, not each author's.",
    )
    suspended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    configuration_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
        comment="JSON-serialized values for the definition's declared fields. "
        "Validated on write and again before a handler is invoked; never "
        "interpreted, and handed back to the pod exactly as supplied.",
    )
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class KnowledgeBaseRunRow(Base):
    """ORM model for the ``knowledge_base_runs`` table.

    What Fred remembers of a run so it can find it again: which instance it
    belongs to and which workflow execution carries it. Deliberately NOT its
    state — that is read from the workflow engine, which is the side Fred runs
    and the only one a killed pod cannot leave wrong.
    """

    __tablename__ = "knowledge_base_runs"

    run_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    instance_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("knowledge_base_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    execution_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Workflow id this run belongs to. With run_id it addresses one "
        "execution in the engine, which is where the run's state is read from.",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
