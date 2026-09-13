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
Knowledge Base definitions: publication by their own image, and Platform Admin
enablement over what was published.

Listing never reaches a pod and never reports availability — a stored
declaration says an image was deployed, not that a worker is running.
Enablement writes the same tuples capability and application enablement write,
through the shared operation in `capabilities.enablement`; this module adds no
second enablement mechanism.
"""

from __future__ import annotations

import logging
from typing import Any

from fred_core import KeycloakUser, prefix_covers
from fred_core.security.rebac.knowledge_base_authz import can_team_use_knowledge_base
from fred_core.security.structure import LOCAL_DEV_CLIENT_ID, is_service_agent
from fred_sdk.knowledge_base import KnowledgeBaseDeclaration
from fred_sdk.knowledge_base.schedule import RunCadence, platform_fields

from control_plane_backend.knowledge_bases.instances import (
    KnowledgeBaseNotEnabled,
    UnknownDefinition,
    create_instance,
    delete_instance,
    displayable_configuration,
    list_instances,
    read_instance,
    require_team_member,
    update_instance,
)
from control_plane_backend.knowledge_bases.runs import list_runs
from control_plane_backend.knowledge_bases.schemas import (
    KnowledgeBaseInstanceCreate,
    KnowledgeBaseInstanceFields,
    KnowledgeBaseInstanceSummary,
    KnowledgeBaseInstanceUpdate,
    KnowledgeBasePublicationResult,
    KnowledgeBaseRunSummary,
)
from control_plane_backend.product.dependencies import ProductServiceDependencies

logger = logging.getLogger(__name__)


class KnowledgeBaseClientMismatch(Exception):
    """Raised when a client publishes a definition bound to a different one."""

    http_status = 403


async def publish_definition(
    *,
    user: KeycloakUser,
    prefix: str,
    declaration: KnowledgeBaseDeclaration,
    deps: ProductServiceDependencies,
) -> KnowledgeBasePublicationResult:
    """Record what an image declares about itself, at deployment time.

    A contributor owns a prefix and publishes as many names under it as it
    wants. The first publication claims that prefix for the calling client;
    every later one must present the same client, so nobody writes under
    another's prefix. The claim itself is enforced in the store, by a row whose
    primary key is the prefix — checking it here would be racy.
    """

    # A workload identity, not a person: without this an ordinary signed-in
    # user's token carries the frontend's `azp` and could publish definitions.
    # The local-dev client is admitted here and ONLY here — a targeted
    # allowance, so that authentication being disabled never turns every local
    # caller into a service identity platform-wide.
    if not is_service_agent(user) and user.client_id != LOCAL_DEV_CLIENT_ID:
        raise KnowledgeBaseClientMismatch(
            "Publishing requires a service identity, not a user session"
        )
    caller = user.client_id
    if not caller:
        raise KnowledgeBaseClientMismatch(
            "Publishing requires a confidential client identity"
        )
    # The same token carries both: `azp` names the client a prefix is bound to,
    # `sub` names the account it authenticates as. Only the second can be the
    # subject of a grant, so it is recorded now rather than looked up in
    # Keycloak's admin API when an instance later needs to hand a pod a library.
    subject = user.uid
    if not subject:
        raise KnowledgeBaseClientMismatch(
            "Publishing requires an identity with a subject"
        )

    if not prefix_covers(prefix, declaration.id):
        raise KnowledgeBaseClientMismatch(
            f"{declaration.id!r} is not under the declared prefix {prefix!r}"
        )

    published = await deps.get_knowledge_base_definition_store().upsert(
        prefix=prefix, declaration=declaration, client_id=caller, subject=subject
    )
    logger.info(
        "[knowledge-base-publication] stored declaration for %s version %s",
        published.id,
        published.version,
    )
    return KnowledgeBasePublicationResult(
        id=published.id, prefix=published.prefix, version=published.version
    )


# ---------------------------------------------------------------------------
# Team instances — a folder that fills itself
# ---------------------------------------------------------------------------


async def definition_fields(
    *, user: KeycloakUser, definition_id: str, team_id: str, deps: Any
) -> KnowledgeBaseInstanceFields:
    """The two zones an instance form renders, for a team that may use this one.

    Read from the stored declaration, so the form is the same whether or not
    the definition's pod is running: a declaration says what an image expects,
    never that anything is up.
    """
    definition = await deps.get_knowledge_base_definition_store().get(definition_id)
    if definition is None:
        raise UnknownDefinition(f"No definition published as {definition_id!r}")
    await require_team_member(user=user, team_id=team_id, deps=deps)
    if not await can_team_use_knowledge_base(
        deps.team_dependencies.rebac, team_id, definition_id=definition_id
    ):
        raise KnowledgeBaseNotEnabled(f"{definition_id!r} is not enabled for this team")
    return KnowledgeBaseInstanceFields(
        definition_id=definition.id,
        definition_name=definition.name,
        platform_fields=platform_fields(),
        configuration_fields=definition.configuration_fields,
    )


async def create_instance_for_team(
    *,
    user: KeycloakUser,
    authorization: str,
    body: KnowledgeBaseInstanceCreate,
    deps: Any,
) -> KnowledgeBaseInstanceSummary:
    await require_team_member(user=user, team_id=body.team_id, deps=deps)
    instance = await create_instance(
        user=user,
        authorization=authorization,
        definition_id=body.definition_id,
        team_id=body.team_id,
        folder_name=body.folder_name,
        cadence=body.cadence,
        suspended=body.suspended,
        configuration=body.configuration,
        deps=deps,
    )
    return await _summarize(instance, deps=deps)


async def read_instance_for_team(
    *, user: KeycloakUser, instance_id: str, deps: Any
) -> KnowledgeBaseInstanceSummary:
    instance = await read_instance(user=user, instance_id=instance_id, deps=deps)
    return await _summarize(instance, deps=deps)


async def list_instances_for_team(
    *, user: KeycloakUser, team_id: str, deps: Any
) -> list[KnowledgeBaseInstanceSummary]:
    instances = await list_instances(user=user, team_id=team_id, deps=deps)
    # Read each definition once: a team with twenty folders of one Knowledge
    # Base would otherwise fetch the same declaration twenty times.
    store = deps.get_knowledge_base_definition_store()
    definitions = {
        definition_id: await store.get(definition_id)
        for definition_id in {instance.definition_id for instance in instances}
    }
    return [
        _summary_of(instance, definitions.get(instance.definition_id))
        for instance in instances
    ]


async def update_instance_for_team(
    *,
    user: KeycloakUser,
    instance_id: str,
    body: KnowledgeBaseInstanceUpdate,
    deps: Any,
) -> KnowledgeBaseInstanceSummary:
    instance = await update_instance(
        user=user,
        instance_id=instance_id,
        cadence=body.cadence,
        suspended=body.suspended,
        configuration=body.configuration,
        deps=deps,
    )
    return await _summarize(instance, deps=deps)


async def delete_instance_for_team(
    *, user: KeycloakUser, authorization: str, instance_id: str, deps: Any
) -> None:
    await delete_instance(
        user=user,
        authorization=authorization,
        instance_id=instance_id,
        deps=deps,
    )


async def list_runs_for_team(
    *, user: KeycloakUser, instance_id: str, deps: Any
) -> list[KnowledgeBaseRunSummary]:
    """Runs of one instance, for a member of its own team and nobody else."""
    instance = await read_instance(user=user, instance_id=instance_id, deps=deps)
    return [
        KnowledgeBaseRunSummary(run_id=run_id, state=state, started_at=started_at)
        for run_id, state, started_at in await list_runs(instance=instance, deps=deps)
    ]


async def _summarize(instance: Any, *, deps: Any) -> KnowledgeBaseInstanceSummary:
    definition = await deps.get_knowledge_base_definition_store().get(
        instance.definition_id
    )
    return _summary_of(instance, definition)


def _summary_of(instance: Any, definition: Any) -> KnowledgeBaseInstanceSummary:
    declared = [] if definition is None else definition.configuration_fields
    return KnowledgeBaseInstanceSummary(
        id=instance.id,
        definition_id=instance.definition_id,
        definition_name=instance.definition_id
        if definition is None
        else definition.name,
        team_id=instance.team_id,
        library_id=instance.library_id,
        library_name=instance.library_name,
        cadence=RunCadence(instance.cadence),
        suspended=instance.suspended,
        configuration=displayable_configuration(instance, declared),
        created_at=instance.created_at,
        updated_at=instance.updated_at,
    )
