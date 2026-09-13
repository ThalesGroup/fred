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
What a run is given, and what Fred says a run did.

Two halves that deliberately never meet. The pod is *given* one run's
configuration, authorized by the exact client its definition is bound to. The
pod is never *asked* what happened: Fred runs the workflow engine, so it
already knows a run started, is still running, ended or crashed, and a pod
killed mid-run would simply never answer — leaving a run that looks unfinished
for ever. Reading the engine instead means there is only ever one version of
that fact.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

from fred_core import KeycloakUser
from fred_core.security.structure import LOCAL_DEV_CLIENT_ID, is_service_agent
from fred_sdk.knowledge_base.models import (
    KnowledgeBaseRunContext,
    KnowledgeBaseRunOutcome,
)
from temporalio.client import WorkflowExecutionStatus
from temporalio.service import RPCError, RPCStatusCode

from control_plane_backend.knowledge_bases.instance_store import KnowledgeBaseInstance
from control_plane_backend.knowledge_bases.validation import (
    validate_instance_configuration,
)

logger = logging.getLogger(__name__)


class RunAccessDenied(Exception):
    """The caller is not the client this definition is bound to."""

    http_status = 403


class RunNotFound(Exception):
    """No such instance under that definition."""

    http_status = 404


class RunState(StrEnum):
    """What an instance shows for one run."""

    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


_TERMINAL_BY_STATUS: dict[Any, RunState] = {
    WorkflowExecutionStatus.FAILED: RunState.failed,
    WorkflowExecutionStatus.TIMED_OUT: RunState.failed,
    WorkflowExecutionStatus.TERMINATED: RunState.failed,
    WorkflowExecutionStatus.CANCELED: RunState.cancelled,
    WorkflowExecutionStatus.CONTINUED_AS_NEW: RunState.running,
    WorkflowExecutionStatus.RUNNING: RunState.running,
}


def require_bound_client(user: KeycloakUser, definition: Any, *, what: str) -> None:
    """Admit only the exact client this definition was published by.

    A broad service role is not enough on its own: every backend workload holds
    one, and the configuration behind this check is where a source's secrets
    are. The local-development client is admitted only where authentication is
    disabled altogether, the same narrow allowance publication makes.
    """
    if not is_service_agent(user) and user.client_id != LOCAL_DEV_CLIENT_ID:
        raise RunAccessDenied(f"{what} requires a service identity")
    if user.client_id == LOCAL_DEV_CLIENT_ID:
        return
    if not user.client_id or user.client_id != definition.client_id:
        raise RunAccessDenied(
            f"{what} is bound to another client than {user.client_id!r}"
        )


async def build_run_context(
    *,
    user: KeycloakUser,
    definition_id: str,
    instance_id: str,
    run_id: str,
    execution_id: str,
    deps: Any,
) -> KnowledgeBaseRunContext:
    """Hand one run its configuration, and remember that the run exists.

    The instance is what scopes the call: a client bound to one definition
    cannot read another's, and an instance that belongs to a different
    definition is not this pod's to fetch — which is what keeps one source's
    secrets away from another's pod.
    """
    definition = await deps.get_knowledge_base_definition_store().get(definition_id)
    if definition is None:
        raise RunNotFound(f"No definition published as {definition_id!r}")
    require_bound_client(user, definition, what="Reading a run's configuration")

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

    await deps.get_knowledge_base_instance_store().record_run(
        run_id=run_id, instance_id=instance_id, execution_id=execution_id
    )
    return KnowledgeBaseRunContext(
        definition_id=definition_id,
        instance_id=instance_id,
        team_id=instance.team_id,
        run_id=run_id,
        library_id=instance.library_id,
        configuration=configuration,
    )


async def resolve_run_state(*, client: Any, execution_id: str, run_id: str) -> RunState:
    """Ask the workflow engine how one run ended.

    Two things are read, and both come from the engine. Its status covers every
    way a run stops without saying anything — crashed, timed out, terminated,
    cancelled, or a pod that simply died. Its result covers the one case a
    status cannot express: a handler that ran to completion and reported a
    business failure, which the engine records as a successful execution.

    A run the engine no longer holds is reported failed rather than missing:
    history has a retention policy, and a run old enough to have fallen out of
    it certainly is not still running.
    """
    handle = client.get_workflow_handle(execution_id, run_id=run_id)
    try:
        description = await handle.describe()
    except RPCError as exc:
        if exc.status == RPCStatusCode.NOT_FOUND:
            logger.info(
                "[knowledge-base] run %s is no longer in the engine's history", run_id
            )
            return RunState.failed
        raise

    status = description.status
    if status != WorkflowExecutionStatus.COMPLETED:
        return _TERMINAL_BY_STATUS.get(status, RunState.running)

    try:
        outcome = await handle.result()
    except Exception:  # noqa: BLE001
        # The execution completed, so this is a decoding problem, not a run
        # problem. Succeeded is what the engine said.
        logger.warning(
            "[knowledge-base] could not read the result of run %s",
            run_id,
            exc_info=True,
        )
        return RunState.succeeded
    return _OUTCOMES.get(str(outcome), RunState.succeeded)


_OUTCOMES: dict[str, RunState] = {
    KnowledgeBaseRunOutcome.succeeded.value: RunState.succeeded,
    KnowledgeBaseRunOutcome.failed.value: RunState.failed,
    KnowledgeBaseRunOutcome.cancelled.value: RunState.cancelled,
}


async def list_runs(
    *, instance: KnowledgeBaseInstance, deps: Any
) -> list[tuple[str, RunState, Any]]:
    """Every run Fred has seen of one instance, with the state the engine gives.

    The state is never stored: a stored one would be a copy that goes stale the
    moment a pod is killed, which is exactly the case it exists to cover.
    """
    records = await deps.get_knowledge_base_instance_store().list_runs(instance.id)
    if not records:
        return []
    client = await deps.get_temporal_client()
    resolved: list[tuple[str, RunState, Any]] = []
    for record in records:
        state = await resolve_run_state(
            client=client, execution_id=record.execution_id, run_id=record.run_id
        )
        resolved.append((record.run_id, state, record.started_at))
    return resolved
