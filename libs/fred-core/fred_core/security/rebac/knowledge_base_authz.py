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
Authorization helpers for configured Knowledge Base definitions.

The authorized object is the definition, and its type is distinct from
`capability` and `app` so neither of their grants can make a Knowledge Base
usable. Instances are not authorization objects: they are team-scoped rows
whose access follows their team.

Three things live here: composing the catalog id, naming the authorization
object, and the two questions instances ask of it — may this team use this
definition, and what grant lets its pod fill one library.
"""

from __future__ import annotations

from fred_core.security.rebac.rebac_engine import (
    KnowledgeBaseDefinitionPermission,
    RebacDisabledResult,
    RebacEngine,
    RebacReference,
    Relation,
    RelationType,
    Resource,
    team_subject_and_context,
)

# Naming, not authorization: these three are pure string work every pod needs,
# so they live in fred-pod and are re-exported here for the call sites that
# already reach for them through the authorization module.
from fred_pod.common.naming import (
    KNOWLEDGE_BASE_CATALOG_NAMESPACE_PREFIX,
    knowledge_base_catalog_id,
    knowledge_base_name_from_catalog_id,
)

__all__ = [
    "KNOWLEDGE_BASE_CATALOG_NAMESPACE_PREFIX",
    "can_team_use_knowledge_base",
    "knowledge_base_catalog_id",
    "knowledge_base_definition_ref",
    "knowledge_base_library_grant",
    "knowledge_base_name_from_catalog_id",
    "usable_knowledge_base_ids",
]


def knowledge_base_definition_ref(name: str) -> RebacReference:
    """Return the typed authorization reference for one definition.

    The object id is the contributed name itself — the catalog key minus its
    namespace prefix, the same relationship `app__<app_id>` has to `app:<id>`.
    """

    return RebacReference(type=Resource.KNOWLEDGE_BASE_DEFINITION, id=name)


async def can_team_use_knowledge_base(
    rebac: RebacEngine, team_id: str, *, definition_id: str
) -> bool:
    """Whether this team may hold an instance of this definition.

    Unlike applications, a personal space is not excluded: a Knowledge Base is
    enabled one definition at a time, for any team, and a personal space is a
    team like another here — nothing reaches every personal space at once.

    A disabled ReBAC engine answers True, which is the established local-dev
    signal: authorization is off, so nothing is refused for lack of it.
    """

    team_ref, context = team_subject_and_context(team_id)
    return await rebac.has_permission(
        team_ref,
        KnowledgeBaseDefinitionPermission.CAN_USE,
        knowledge_base_definition_ref(definition_id),
        contextual_relations=context,
        consistency_token=RebacEngine.HIGHER_CONSISTENCY,
    )


async def usable_knowledge_base_ids(
    rebac: RebacEngine, team_id: str
) -> set[str] | None:
    """Return the definitions one team may use, in a single question.

    Asking `can_team_use_knowledge_base` once per published definition is the
    shape that made listing capabilities slow; a listing must not pay one round
    trip per row. ``None`` retains the established disabled-ReBAC signal.
    """

    team_ref, context = team_subject_and_context(team_id)
    refs = await rebac.lookup_resources(
        team_ref,
        KnowledgeBaseDefinitionPermission.CAN_USE,
        Resource.KNOWLEDGE_BASE_DEFINITION,
        contextual_relations=context,
        consistency_token=RebacEngine.HIGHER_CONSISTENCY,
    )
    if isinstance(refs, RebacDisabledResult):
        return None
    return {ref.id for ref in refs}


def knowledge_base_library_grant(subject: str, library_id: str) -> Relation:
    """The one right a Knowledge Base pod needs, over one library.

    `editor` on a tag is what `update` resolves through, and `update` inherits
    downward through `parent`, so this single statement reaches every folder
    nested under that library and nothing outside it. The subject is the pod's
    service account — a client cannot be the subject of a relation, which is
    why a publication records the account behind it.

    Never a team-level right: that would let a pod write into the folder beside
    its own, in the same team, and the whole point of granting it here rather
    than at deployment is that a team decides which folders it may fill.
    """

    return Relation(
        subject=RebacReference(type=Resource.USER, id=subject),
        relation=RelationType.EDITOR,
        resource=RebacReference(type=Resource.TAGS, id=library_id),
    )
