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
Team-subject `can_use` knowledge-base-type query (docs/swift/rfc/KNOWLEDGE-BASE-RFC.md §6).

Mirrors `capability_authz.py`'s `can_team_use_capability`, on the separate
`knowledge_base_type` object type — not merged into that module because a
knowledge base type is not "something an agent uses" (same reasoning as the
equivalent, in-progress move for `app`). No personal-space class overlay
here: unlike `capability`, `knowledge_base_type` defines no
`personal_on`/`personal_disabled` relations (schema.fga), so there is
nothing for a `organization#personal_team` contextual edge to resolve
against.

The check SUBJECT IS THE TEAM creating/operating the knowledge base
instance, never the browsing user — same reasoning as `capability_authz.py`.
"""

from __future__ import annotations

from fred_core.security.models import Resource
from fred_core.security.rebac.rebac_engine import (
    ORGANIZATION_ID,
    KnowledgeBaseTypePermission,
    RebacEngine,
    RebacReference,
    Relation,
    RelationType,
)


async def can_team_use_knowledge_base_type(
    rebac: RebacEngine, team_id: str, *, knowledge_base_type_id: str
) -> bool:
    """One team, one knowledge base type: may `team_id` create/operate an instance of it?

    With ReBAC disabled the engine answers `True`, matching an unfiltered catalog.
    """

    team_ref = RebacReference(type=Resource.TEAM, id=team_id)
    org_ref = RebacReference(type=Resource.ORGANIZATION, id=ORGANIZATION_ID)
    context = [Relation(subject=team_ref, relation=RelationType.TEAM, resource=org_ref)]
    return await rebac.has_permission(
        team_ref,
        KnowledgeBaseTypePermission.CAN_USE,
        RebacReference(type=Resource.KNOWLEDGE_BASE_TYPE, id=knowledge_base_type_id),
        contextual_relations=context,
    )
