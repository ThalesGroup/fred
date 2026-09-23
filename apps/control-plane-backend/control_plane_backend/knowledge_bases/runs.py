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
What a run is given.

The pod is given one run's configuration and is never asked what happened:
Fred owns the workflow engine, so the engine's own history is the single
account of whether a run started, finished or crashed.
"""

from __future__ import annotations

from typing import Any

from fred_core import KeycloakUser, get_delegation_config
from fred_core.security.structure import LOCAL_DEV_CLIENT_ID, is_service_agent
from fred_sdk.knowledge_base.models import KnowledgeBaseRunContext

from control_plane_backend.knowledge_bases.validation import (
    validate_instance_configuration,
)


class RunAccessDenied(Exception):
    """The caller is not the client this definition is bound to."""

    http_status = 403


class RunNotFound(Exception):
    """No such instance under that definition."""

    http_status = 404


async def build_run_context(
    *,
    user: KeycloakUser,
    definition_id: str,
    instance_id: str,
    run_id: str,
    deps: Any,
) -> KnowledgeBaseRunContext:
    """Hand one run its configuration.

    The instance is what scopes the call: a client bound to one definition
    cannot read another's, and an instance that belongs to a different
    definition is not this pod's to fetch — which is what keeps one source's
    secrets away from another's pod.
    """
    definition = await deps.get_knowledge_base_definition_store().get(definition_id)
    if definition is None:
        raise RunNotFound(f"No definition published as {definition_id!r}")

    # A broad service role is not enough on its own: every backend workload
    # holds one, and the configuration behind this check is where a source's
    # secrets are.
    if (
        not get_delegation_config().enabled
        and not is_service_agent(user)
        and user.client_id != LOCAL_DEV_CLIENT_ID
    ):
        raise RunAccessDenied(
            "Reading a run's configuration requires a service identity"
        )
    if user.client_id != LOCAL_DEV_CLIENT_ID and (
        not user.client_id or user.client_id != definition.client_id
    ):
        raise RunAccessDenied(
            f"Reading a run's configuration is bound to another client "
            f"than {user.client_id!r}"
        )

    instance = await deps.get_knowledge_base_instance_store().get(instance_id)
    if instance is None or instance.definition_id != definition_id:
        raise RunNotFound(f"No instance {instance_id!r} of {definition_id!r}")

    # Validated again, with the same code that accepted it: a definition
    # republished with different declared fields leaves stored values that were
    # valid when written, and a handler promised validated configuration should
    # not be the one to find out otherwise.
    configuration = validate_instance_configuration(
        definition.configuration_fields, instance.configuration
    )

    return KnowledgeBaseRunContext(
        definition_id=definition_id,
        instance_id=instance_id,
        team_id=instance.team_id,
        run_id=run_id,
        library_id=instance.library_id,
        configuration=configuration,
    )
