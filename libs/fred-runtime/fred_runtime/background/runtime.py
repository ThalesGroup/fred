"""Bridge durable workflow admission into the normal in-process agent executor."""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator, Mapping
from typing import Any, cast

from fastapi import HTTPException
from fred_core.scheduler import SchedulerBackend
from fred_core.security.delegation import AssertedUser
from fred_core.security.models import StandingAuthorizationError
from fred_core.tasks.agent_run import AgentRunAdmissionRecord
from fred_sdk.contracts.context import RuntimeContext
from fred_sdk.contracts.execution import RuntimeExecuteRequest
from fred_sdk.contracts.models import GraphAgentDefinition, ReActAgentDefinition

from fred_runtime.app.agent_app import (
    _authorize_and_resolve,
    _finish_admitted_run,
    _iterate_runtime_event_payloads,
)
from fred_runtime.app.config import PodSchedulerConfig
from fred_runtime.app.context import PodApplicationContext
from fred_runtime.background.activities import (
    AgentRunExecutor,
    AgentRunRegistrationError,
)
from fred_runtime.capabilities import CapabilityRegistry
from fred_runtime.common.outbound_credentials import (
    DelegatedCredentialProvider,
    ImmutableRunRecordSource,
    RunRecord,
    get_delegation_runtime,
)
from fred_runtime.runtime_support.run_budget import RunLimits


def validate_background_scheduler(config: PodSchedulerConfig) -> None:
    """Fail closed for this worker without changing generic scheduler semantics."""
    if not config.enabled:
        raise ValueError("Background agent-run worker is disabled.")
    if config.backend != SchedulerBackend.TEMPORAL:
        raise ValueError("Background agent runs require the Temporal scheduler.")
    if not config.temporal.task_queue.strip():
        raise ValueError("Background agent runs require a Temporal task queue.")


def build_background_agent_executor(
    *,
    container: PodApplicationContext,
    registry: Mapping[str, ReActAgentDefinition | GraphAgentDefinition],
    capability_registry: CapabilityRegistry,
) -> AgentRunExecutor:
    """Create the workflow hook while reusing normal authorization and execution."""

    async def execute(record: AgentRunAdmissionRecord) -> AsyncIterator[dict[str, Any]]:
        delegation = get_delegation_runtime()
        caller = delegation.workload_client_id if delegation is not None else None
        if delegation is None or not delegation.enabled or not caller:
            raise AgentRunRegistrationError()

        request = RuntimeExecuteRequest(
            agent_instance_id=record.agent_instance_id,
            input=record.prompt,
            runtime_context=RuntimeContext(
                user_id=record.person_id,
                team_id=record.team_id,
                agent_instance_id=record.agent_instance_id,
                template_agent_id=record.agent_id,
                selected_document_uids=list(record.scope.document_ids) or None,
                selected_document_libraries_ids=list(record.scope.library_ids) or None,
            ),
        )
        asserted = AssertedUser(
            uid=record.person_id,
            client_id=caller,
            run_id=record.run_id,
            agent_id=record.agent_instance_id,
        )
        admission_limits = RunLimits(
            record.budget.wall_clock_seconds,
            record.budget.max_concurrent_children,
        )
        try:
            internal, target = await _authorize_and_resolve(
                request,
                authenticated_user=asserted,
                container=container,
                registry=registry,
                access_token=None,
                admission_limits=admission_limits,
            )
        except HTTPException as exc:
            if exc.status_code == 403:
                raise StandingAuthorizationError() from None
            raise AgentRunRegistrationError() from exc
        except Exception as exc:
            raise AgentRunRegistrationError() from exc

        provider = target.credential_provider
        if not isinstance(provider, DelegatedCredentialProvider):
            raise AgentRunRegistrationError()
        try:
            if target.definition.agent_id != record.agent_id:
                raise AgentRunRegistrationError()

            local = provider.record
            durable = RunRecord(
                run_id=record.run_id,
                person_id=record.person_id,
                agent_id=local.agent_id,
                agent_instance_id=record.agent_instance_id,
                roles=record.roles,
                team_id=record.team_id,
                mode=record.mode,
                started_at=local.started_at,
                started_monotonic=local.started_monotonic,
                run_ceiling_seconds=local.run_ceiling_seconds,
                origin_caller=caller,
                registered=local.registered,
            )
            provider = provider.with_record_source(
                ImmutableRunRecordSource(durable), root_agent_id=local.agent_id
            )
        except Exception:
            await _finish_admitted_run(provider, "failed", "registration_failed")
            raise AgentRunRegistrationError() from None

        iterator = cast(
            AsyncGenerator[dict[str, Any], None],
            _iterate_runtime_event_payloads(
                target.definition,
                internal,
                access_token=None,
                team_id=record.team_id,
                registry=registry,
                tuning=target.tuning,
                capability_registry=capability_registry,
                team_settings=target.team_settings,
                reasoning_enabled_model_ids=target.reasoning_enabled_model_ids,
                platform_chat_model_binding=target.platform_chat_model_binding,
                platform_prompt=target.platform_prompt,
                credential_provider=provider,
                owns_run_record=True,
                run_limits=target.run_limits,
                run_started_at=target.run_started_at,
            ),
        )
        try:
            async for payload in iterator:
                yield payload
        finally:
            await iterator.aclose()

    return execute
