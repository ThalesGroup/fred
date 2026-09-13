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
Creating a folder that fills itself, and undoing it.

Four things happen, or none does: the library, the instance that records it,
the grant that lets its pod write there, and the cadence Fred runs it on. A
library its pod cannot write to is useless, and a grant over no library is a
standing right with no purpose — so neither is allowed to exist alone.

None of the four share a transaction. Two are rows in one database, one is a
statement in the authorization engine and one is a schedule in the workflow
engine, and nothing spans all three. What holds instead is an order and an
undo: each step is applied only after the previous one succeeded, and a failure
runs the completed steps backwards before the error reaches the caller. The
durable row is written last, so a process that dies mid-way leaves no instance
— the user sees the creation fail, and what remains behind it is at worst an
empty folder they can see and delete.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from fred_core import KeycloakUser
from fred_core.security.models import AuthorizationError
from fred_core.security.rebac.knowledge_base_authz import (
    can_team_use_knowledge_base,
    knowledge_base_library_grant,
)
from fred_sdk.contracts.models import TuningValue
from fred_sdk.knowledge_base.schedule import RunCadence

from control_plane_backend.knowledge_bases.cadence import (
    drop_cadence,
    register_cadence,
)
from control_plane_backend.knowledge_bases.instance_store import KnowledgeBaseInstance
from control_plane_backend.knowledge_bases.library import LibraryClient
from control_plane_backend.knowledge_bases.validation import (
    InstanceConfigurationInvalid,
    validate_instance_configuration,
)

logger = logging.getLogger(__name__)


class KnowledgeBaseNotEnabled(Exception):
    """The team may not hold an instance of this definition."""

    http_status = 403


class KnowledgeBaseInstanceNotFound(Exception):
    """No such instance, or none this caller may see."""

    http_status = 404


class UnknownDefinition(Exception):
    """No definition was ever published under that name."""

    http_status = 404


class KnowledgeBasePodIdentityMissing(Exception):
    """The definition's publication recorded no account to grant.

    A prefix claimed before the subject was recorded, and never republished.
    Refusing is the only safe answer: creating the folder anyway would hand a
    team a library nothing can fill.
    """

    http_status = 409


class _Undo:
    """Steps to run backwards if a later one fails.

    Every undo is best-effort and logged: the error worth raising is the one
    that interrupted the creation, not a failure to tidy up after it.
    """

    def __init__(self) -> None:
        self._steps: list[tuple[str, Callable[[], Awaitable[Any]]]] = []

    def after(self, label: str, step: Callable[[], Awaitable[Any]]) -> None:
        self._steps.append((label, step))

    async def run(self) -> None:
        for label, step in reversed(self._steps):
            try:
                await step()
            except Exception:  # noqa: BLE001
                logger.warning(
                    "[knowledge-base] could not undo %s after a failed creation; "
                    "it may need clearing by hand",
                    label,
                    exc_info=True,
                )


async def create_instance(
    *,
    user: KeycloakUser,
    authorization: str,
    definition_id: str,
    team_id: str,
    folder_name: str,
    cadence: RunCadence,
    suspended: bool,
    configuration: dict[str, Any],
    deps: Any,
) -> KnowledgeBaseInstance:
    """Create the library, the instance, the grant and the cadence, or nothing."""
    definitions = deps.get_knowledge_base_definition_store()
    definition = await definitions.get(definition_id)
    if definition is None:
        raise UnknownDefinition(f"No definition published as {definition_id!r}")

    rebac = deps.team_dependencies.rebac
    if not await can_team_use_knowledge_base(
        rebac, team_id, definition_id=definition_id
    ):
        raise KnowledgeBaseNotEnabled(f"{definition_id!r} is not enabled for this team")
    if not definition.subject:
        raise KnowledgeBasePodIdentityMissing(
            f"{definition_id!r} recorded no service account; redeploy its image "
            "so its publication records one"
        )

    values = validate_instance_configuration(
        definition.configuration_fields, configuration
    )

    # Minted here rather than by the database: the grant and the cadence both
    # name the instance, and both are applied before any row exists.
    instance_id = uuid4().hex
    undo = _Undo()
    try:
        library_id = await LibraryClient(
            deps.configuration.platform.knowledge_flow_base_url, authorization
        ).create(
            name=folder_name,
            team_id=team_id,
            description=f"Synchronized by {definition.name}",
        )
        undo.after(
            f"library {library_id}",
            lambda: LibraryClient(
                deps.configuration.platform.knowledge_flow_base_url, authorization
            ).delete(library_id),
        )

        grant = knowledge_base_library_grant(definition.subject, library_id)
        await rebac.add_relation(grant, actor_uid=user.uid)
        undo.after(
            f"grant over library {library_id}", lambda: rebac.delete_relation(grant)
        )

        client = await deps.get_temporal_client()
        temporal_config = deps.configuration.scheduler.temporal
        await register_cadence(
            client,
            temporal_config,
            instance_id=instance_id,
            definition_id=definition_id,
            team_id=team_id,
            cadence=cadence,
            suspended=suspended,
            max_attempts=deps.configuration.knowledge_bases.run_max_attempts,
        )
        undo.after(
            f"cadence for instance {instance_id}",
            lambda: drop_cadence(client, temporal_config, instance_id=instance_id),
        )

        # Last, and the only durable record: until it commits, nothing Fred
        # keeps says this instance exists.
        return await deps.get_knowledge_base_instance_store().create(
            instance_id=instance_id,
            definition_id=definition_id,
            team_id=team_id,
            library_id=library_id,
            library_name=folder_name,
            cadence=cadence.value,
            suspended=suspended,
            configuration=values,
            granted_subject=definition.subject,
            created_by=user.uid,
        )
    except Exception:
        await undo.run()
        raise


def _carry_secrets_forward(
    declared: list[Any], *, submitted: dict[str, Any], stored: KnowledgeBaseInstance
) -> dict[str, Any]:
    """Keep a secret the submission left empty.

    A display read never returns a secret, so a form round-trip comes back
    without it. Taking that as "cleared" would destroy the value on any edit —
    and refuse the edit outright when the field is required. An empty secret
    field therefore means "unchanged", and clearing one is not offered here.
    """
    carried = dict(submitted)
    held = stored.configuration
    for field in declared:
        if str(field.type) != "secret" or carried.get(field.key) is not None:
            continue
        if field.key in held:
            carried[field.key] = held[field.key]
    return carried


async def update_instance(
    *,
    user: KeycloakUser,
    instance_id: str,
    cadence: RunCadence,
    suspended: bool,
    configuration: dict[str, Any],
    deps: Any,
) -> KnowledgeBaseInstance:
    """Change what an instance runs on and with, leaving its library alone."""
    instance = await _readable_instance(user=user, instance_id=instance_id, deps=deps)
    definition = await deps.get_knowledge_base_definition_store().get(
        instance.definition_id
    )
    if definition is None:
        raise UnknownDefinition(
            f"No definition published as {instance.definition_id!r}"
        )
    values = validate_instance_configuration(
        definition.configuration_fields,
        _carry_secrets_forward(
            definition.configuration_fields, submitted=configuration, stored=instance
        ),
    )

    client = await deps.get_temporal_client()
    # Register rather than update: it creates or aligns, so an instance whose
    # schedule has gone missing is repaired by the next edit instead of failing
    # every one of them for ever.
    await register_cadence(
        client,
        deps.configuration.scheduler.temporal,
        instance_id=instance_id,
        definition_id=instance.definition_id,
        team_id=instance.team_id,
        cadence=cadence,
        suspended=suspended,
        max_attempts=deps.configuration.knowledge_bases.run_max_attempts,
    )
    updated = await deps.get_knowledge_base_instance_store().update(
        instance_id,
        cadence=cadence.value,
        suspended=suspended,
        configuration=values,
    )
    if updated is None:  # pragma: no cover - read under the same request
        raise KnowledgeBaseInstanceNotFound(instance_id)
    return updated


async def delete_instance(
    *,
    user: KeycloakUser,
    authorization: str,
    instance_id: str,
    deps: Any,
) -> None:
    """Undo a creation, taking the documents with it.

    The library goes FIRST, because it is the step that asks whether this
    person may delete anything at all: knowledge-flow checks the right to
    delete that folder, and a member who does not hold it must be refused
    before the schedule and the grant are torn off an instance that then
    survives — visible, never running, and unfillable.

    The row goes last, for the same reason it was written last: while it
    exists the deletion can be asked for again, and every step below is safe
    to repeat. Stopping a synchronization while keeping what it brought is
    deliberately not offered — deleting the folder is deleting its documents.
    """
    instance = await _readable_instance(user=user, instance_id=instance_id, deps=deps)

    await LibraryClient(
        deps.configuration.platform.knowledge_flow_base_url, authorization
    ).delete(instance.library_id)

    client = await deps.get_temporal_client()
    await drop_cadence(
        client, deps.configuration.scheduler.temporal, instance_id=instance_id
    )

    # The account recorded when the grant was written, not whatever the
    # definition names today: a republication can move a definition onto a new
    # service account, and deleting the relation that exists is the only way to
    # leave none behind.
    if instance.granted_subject:
        await deps.team_dependencies.rebac.delete_relation(
            knowledge_base_library_grant(instance.granted_subject, instance.library_id)
        )

    await deps.get_knowledge_base_instance_store().delete(instance_id)


async def list_instances(
    *, user: KeycloakUser, team_id: str, deps: Any
) -> list[KnowledgeBaseInstance]:
    """Every synchronized folder of one team the caller belongs to."""
    await require_team_member(user=user, team_id=team_id, deps=deps)
    return await deps.get_knowledge_base_instance_store().list_for_team(team_id)


async def read_instance(
    *, user: KeycloakUser, instance_id: str, deps: Any
) -> KnowledgeBaseInstance:
    return await _readable_instance(user=user, instance_id=instance_id, deps=deps)


def displayable_configuration(
    instance: KnowledgeBaseInstance, declared: list[Any]
) -> dict[str, TuningValue]:
    """The instance's configuration with every secret-declared value removed.

    A read meant for display never carries one back: the form shows an empty
    secret field, and leaving it empty keeps what is stored.
    """
    secrets = {field.key for field in declared if str(field.type) == "secret"}
    return {
        key: value
        for key, value in instance.configuration.items()
        if key not in secrets
    }


async def _readable_instance(
    *, user: KeycloakUser, instance_id: str, deps: Any
) -> KnowledgeBaseInstance:
    instance = await deps.get_knowledge_base_instance_store().get(instance_id)
    if instance is None:
        raise KnowledgeBaseInstanceNotFound(instance_id)
    await require_team_member(user=user, team_id=instance.team_id, deps=deps)
    return instance


async def require_team_member(*, user: KeycloakUser, team_id: str, deps: Any) -> None:
    """An instance is its team's, and follows the team's own membership.

    Instances are not authorization objects of their own: the definition is
    (that is what enablement grants), and everything an instance holds belongs
    to the team that created it.
    """
    from fred_core.security.rebac.rebac_engine import TeamPermission

    try:
        await deps.team_dependencies.rebac.check_user_team_permission_or_raise(
            user=user,
            permission=TeamPermission.CAN_READ,
            team_id=team_id,
        )
    except AuthorizationError:
        # Not found rather than forbidden: whether a team holds an instance is
        # itself the team's business.
        raise KnowledgeBaseInstanceNotFound(team_id) from None


__all__ = [
    "InstanceConfigurationInvalid",
    "KnowledgeBaseInstanceNotFound",
    "KnowledgeBaseNotEnabled",
    "KnowledgeBasePodIdentityMissing",
    "UnknownDefinition",
    "create_instance",
    "require_team_member",
    "delete_instance",
    "displayable_configuration",
    "list_instances",
    "read_instance",
    "update_instance",
]
