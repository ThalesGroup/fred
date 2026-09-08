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
Team-scoped knowledge base creation (docs/swift/rfc/KNOWLEDGE-BASE-RFC.md §2/§4/§6).

The one place a `KnowledgeBase` instance gets created — `KnowledgeBaseStore.create`
itself enforces nothing, by design (RFC §4: cross-checking against a
`KnowledgeBaseType` is a service-layer concern, not either pure data model's).
"""

from __future__ import annotations

import uuid

from fred_core.common import TeamId
from fred_core.security.rebac.knowledge_base_type_authz import (
    can_team_use_knowledge_base_type,
)
from fred_core.security.rebac.rebac_engine import RebacEngine
from fred_sdk.contracts.knowledge_base import KnowledgeBase, KnowledgeBaseScope

from control_plane_backend.knowledge_base.store import KnowledgeBaseStore
from control_plane_backend.knowledge_base_types.catalog import (
    KnowledgeBaseTypeCatalogSource,
)


class KnowledgeBaseTypeNotFound(Exception):
    """A `knowledge_base_type_id` this deployment does not register, or has parked (`enabled: false`)."""

    http_status = 404


class KnowledgeBaseTypeAccessDenied(Exception):
    """A team without `can_use` on the knowledge base type (RFC §6) — `fred_core.security.models.AuthorizationError`
    is a user-subject exception; this check's subject is the team, same reasoning as
    `routing_policy/service.py`'s own `ProfileNotUsableError` for `can_team_use_capability`."""

    http_status = 403


async def create_knowledge_base(
    *,
    rebac: RebacEngine,
    store: KnowledgeBaseStore,
    catalog_source: KnowledgeBaseTypeCatalogSource,
    team_id: TeamId,
    knowledge_base_type_id: str,
    name: str,
    tag_ids: list[str],
    connector_ref: str | None,
) -> KnowledgeBase:
    """Create one team-scoped knowledge base instance.

    Fails closed on two independent checks, in order: the knowledge base
    type must be registered and enabled in this deployment
    (`KnowledgeBaseTypeNotFound`), then the team must hold `can_use` on it
    (`KnowledgeBaseTypeAccessDenied`, RFC §6).
    """

    catalog = catalog_source.load()
    if not any(
        item.knowledge_base_type_id == knowledge_base_type_id for item in catalog.items
    ):
        raise KnowledgeBaseTypeNotFound(knowledge_base_type_id)

    if not await can_team_use_knowledge_base_type(
        rebac, str(team_id), knowledge_base_type_id=knowledge_base_type_id
    ):
        raise KnowledgeBaseTypeAccessDenied(
            f"Team {team_id} may not use knowledge base type {knowledge_base_type_id!r}"
        )

    knowledge_base = KnowledgeBase(
        knowledge_base_id=str(uuid.uuid4()),
        name=name,
        knowledge_base_type_id=knowledge_base_type_id,
        scope=KnowledgeBaseScope(team_id=str(team_id), tag_ids=tag_ids),
        connector_ref=connector_ref,
    )
    return await store.create(knowledge_base)
