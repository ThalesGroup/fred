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

"""
Pure CRUD over ``knowledge_base_definitions``.

Select-then-write upsert, like the other control-plane stores, so the local
SQLite dev database and Postgres behave the same. Authorization — including
the client binding — is the service layer's job, never this store's.
"""

from __future__ import annotations

import json
import logging

from fred_core.sql import make_session_factory, use_session
from fred_sdk.contracts.models import FieldSpec
from fred_sdk.knowledge_base import KnowledgeBaseDeclaration
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.models.knowledge_base_models import (
    KnowledgeBaseDefinitionRow,
    KnowledgeBasePrefixRow,
)

logger = logging.getLogger(__name__)


class KnowledgeBasePrefixConflict(Exception):
    """A client published a name under a prefix another client owns."""

    http_status = 403


class PublishedDefinition:
    """One stored declaration."""

    def __init__(self, row: KnowledgeBaseDefinitionRow) -> None:
        self.id = row.id
        self.prefix = row.prefix
        self.version = row.version
        self.name = row.name
        self.description = row.description
        self._configuration_fields_json = row.configuration_fields_json

    @property
    def configuration_fields(self) -> list[FieldSpec]:
        """Parsed on demand: the capability-catalog projection never reads it,
        and that projection runs on every admin list and every mutation."""

        return [
            FieldSpec.model_validate(field)
            for field in json.loads(self._configuration_fields_json)
        ]


class KnowledgeBaseDefinitionStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def upsert(
        self,
        *,
        prefix: str,
        declaration: KnowledgeBaseDeclaration,
        client_id: str,
        session: AsyncSession | None = None,
    ) -> PublishedDefinition:
        """Replace this definition's row wholesale, inside the prefix claim.

        No history of previous declarations is kept and nothing compares a
        publication against what it replaces: a changed set of declared fields
        is an operator sequence (delete the instances first), not something
        Fred reconciles.
        """
        async with use_session(self._sessions, session) as active:
            await self._claim_prefix(active, prefix, client_id)
            row = await active.get(KnowledgeBaseDefinitionRow, declaration.id)
            if row is None:
                row = KnowledgeBaseDefinitionRow(id=declaration.id, prefix=prefix)
                active.add(row)
            elif row.prefix != prefix:
                # A name belongs to one prefix for life. Letting a shorter or
                # longer prefix adopt it would move it between owners silently.
                raise KnowledgeBasePrefixConflict(
                    f"{declaration.id!r} already belongs to prefix {row.prefix!r}"
                )
            row.version = declaration.version
            row.name = declaration.name
            row.description = declaration.description
            row.configuration_fields_json = json.dumps(
                [
                    field.model_dump(mode="json", exclude_none=True)
                    for field in declaration.configuration_fields
                ]
            )
            await active.flush()
            return PublishedDefinition(row)

    @staticmethod
    async def _claim_prefix(active: AsyncSession, prefix: str, client_id: str) -> None:
        """Claim the prefix for this client, or verify it already holds it.

        The claim is a row whose primary key IS the prefix, so two pods claiming
        it at the same instant collide in PostgreSQL — one commits, the other is
        refused. An application-level check could not do this: it would read
        "unclaimed" in both transactions and let both write.
        """

        owner = await active.get(KnowledgeBasePrefixRow, prefix)
        if owner is not None:
            if owner.client_id != client_id:
                raise KnowledgeBasePrefixConflict(
                    f"Prefix {prefix!r} is owned by another client"
                )
            return

        active.add(KnowledgeBasePrefixRow(prefix=prefix, client_id=client_id))
        try:
            await active.flush()
        except IntegrityError as exc:
            raise KnowledgeBasePrefixConflict(
                f"Prefix {prefix!r} was claimed concurrently"
            ) from exc

    async def get(
        self,
        name: str,
        *,
        session: AsyncSession | None = None,
    ) -> PublishedDefinition | None:
        async with use_session(self._sessions, session) as active:
            row = await active.get(KnowledgeBaseDefinitionRow, name)
            return None if row is None else PublishedDefinition(row)

    async def list_all(
        self, *, session: AsyncSession | None = None
    ) -> list[PublishedDefinition]:
        async with use_session(self._sessions, session) as active:
            rows = await active.scalars(
                select(KnowledgeBaseDefinitionRow).order_by(
                    KnowledgeBaseDefinitionRow.id
                )
            )
            return [PublishedDefinition(row) for row in rows]
