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
)

logger = logging.getLogger(__name__)


class KnowledgeBaseProviderConflict(Exception):
    """A client published into a provider namespace bound to another client."""

    http_status = 403


class PublishedDefinition:
    """One stored declaration, with the client bound to it."""

    def __init__(self, row: KnowledgeBaseDefinitionRow) -> None:
        self.provider_id = row.provider_id
        self.definition_id = row.definition_id
        self.client_id = row.client_id
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
        provider_id: str,
        declaration: KnowledgeBaseDeclaration,
        client_id: str,
        session: AsyncSession | None = None,
    ) -> PublishedDefinition:
        """Replace this definition's row wholesale, inside the binding check.

        The check lives HERE, in the transaction that writes, not in the caller:
        reading the owner in one transaction and writing in another lets two
        concurrent first publications both see "unclaimed" and the loser
        silently overwrite the winner's content.

        No history of previous declarations is kept and nothing compares a
        publication against what it replaces: a changed set of declared fields
        is an operator sequence (delete the instances first), not something
        Fred reconciles.
        """
        async with use_session(self._sessions, session) as active:
            await self._require_provider_binding(active, provider_id, client_id)
            row = await active.get(
                KnowledgeBaseDefinitionRow, (provider_id, declaration.id)
            )
            if row is None:
                row = KnowledgeBaseDefinitionRow(
                    provider_id=provider_id,
                    definition_id=declaration.id,
                    client_id=client_id,
                )
                active.add(row)
            row.version = declaration.version
            row.name = declaration.name
            row.description = declaration.description
            row.configuration_fields_json = json.dumps(
                [
                    field.model_dump(mode="json", exclude_none=True)
                    for field in declaration.configuration_fields
                ]
            )
            try:
                await active.flush()
            except IntegrityError as exc:
                # Another first publication for the same provider committed
                # between the check above and this flush. Re-run the check so
                # a different client gets the refusal, never a raw SQL error.
                raise KnowledgeBaseProviderConflict(
                    f"Provider {provider_id!r} was claimed concurrently"
                ) from exc
            return PublishedDefinition(row)

    @staticmethod
    async def _require_provider_binding(
        active: AsyncSession, provider_id: str, client_id: str
    ) -> None:
        """Refuse a client writing into a provider namespace bound elsewhere.

        One provider, one client: any row already stored for this provider
        names its owner, so a single lookup decides.
        """

        owner = await active.scalar(
            select(KnowledgeBaseDefinitionRow.client_id)
            .where(KnowledgeBaseDefinitionRow.provider_id == provider_id)
            .limit(1)
        )
        if owner is not None and owner != client_id:
            raise KnowledgeBaseProviderConflict(
                f"Provider {provider_id!r} is bound to another client"
            )

    async def get(
        self,
        provider_id: str,
        definition_id: str,
        *,
        session: AsyncSession | None = None,
    ) -> PublishedDefinition | None:
        async with use_session(self._sessions, session) as active:
            row = await active.get(
                KnowledgeBaseDefinitionRow, (provider_id, definition_id)
            )
            return None if row is None else PublishedDefinition(row)

    async def list_all(
        self, *, session: AsyncSession | None = None
    ) -> list[PublishedDefinition]:
        async with use_session(self._sessions, session) as active:
            rows = await active.scalars(
                select(KnowledgeBaseDefinitionRow).order_by(
                    KnowledgeBaseDefinitionRow.provider_id,
                    KnowledgeBaseDefinitionRow.definition_id,
                )
            )
            return [PublishedDefinition(row) for row in rows]
