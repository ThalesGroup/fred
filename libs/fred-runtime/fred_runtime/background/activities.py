from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timezone

from fred_core.security.models import AuthorizationError, StandingAuthorizationError
from fred_core.security.rebac.rebac_engine import RebacEngine, TeamPermission
from fred_core.security.structure import KeycloakUser
from fred_core.tasks.agent_run import (
    AgentRunAdmissionRecord,
    AgentRunWorkflowInputV1,
    ScheduledAgentRunInputV1,
    ScheduledAgentRunOccurrence,
    ScheduledAgentRunOccurrenceRequest,
)
from fred_core.tasks.models import (
    AgentRunDetail,
    AgentRunReason,
    AgentRunTaskEvent,
    TaskState,
)
from temporalio import activity

from fred_runtime.background.reporter import AgentRunReporter

AgentRunExecutor = Callable[[AgentRunAdmissionRecord], AsyncIterator[dict[str, object]]]


class AgentRunRegistrationError(RuntimeError):
    pass


class AgentRunDelegationUnavailableError(RuntimeError):
    pass


class AgentRunActivities:
    def __init__(
        self,
        *,
        rebac: RebacEngine,
        executor: AgentRunExecutor,
        reporter: AgentRunReporter,
    ) -> None:
        self._rebac = rebac
        self._executor = executor
        self._reporter = reporter

    async def _report(
        self,
        task_id: str,
        state: TaskState,
        sequence: int,
        reason: AgentRunReason | None = None,
    ) -> int:
        await self._reporter.record(
            task_id,
            AgentRunTaskEvent(
                task_id=task_id,
                state=state,
                seq=sequence + 1,
                timestamp=datetime.now(timezone.utc),
                detail=AgentRunDetail(mode="background", reason=reason),
                error=None
                if state != TaskState.failed
                else "Background agent run failed",
            ),
        )
        return sequence + 1

    @activity.defn(name="fred.execute_background_agent_run.v1")
    async def execute(self, value: AgentRunWorkflowInputV1) -> None:
        record = value.record
        sequence = 0
        try:
            await self._rebac.require_user_standing(record.person_id)
            user = KeycloakUser(
                uid=record.person_id,
                username=record.person_id,
                email=None,
                roles=list(record.roles),
            )
            await self._rebac.check_user_team_permission_or_raise(
                user, TeamPermission.CAN_USE_TEAM_AGENTS, team_id=record.team_id
            )
            sequence = await self._report(value.task_id, TaskState.running, sequence)

            async def consume() -> tuple[TaskState, AgentRunReason]:
                state = TaskState.failed
                reason: AgentRunReason = "execution_failed"
                iterator = self._executor(record)
                try:
                    async for payload in iterator:
                        activity.heartbeat()
                        kind = payload.get("kind")
                        if kind == "final":
                            state, reason = TaskState.succeeded, "completed"
                            break
                        if kind == "execution_error":
                            raw_reason = payload.get("reason")
                            if raw_reason == "cancelled":
                                state, reason = TaskState.cancelled, "cancelled"
                            elif raw_reason in (
                                "authority_lost",
                                "registration_failed",
                                "delegation_unavailable",
                                "run_ceiling_reached",
                                "child_limit_reached",
                            ):
                                state, reason = TaskState.failed, raw_reason
                            else:
                                state, reason = TaskState.failed, "execution_failed"
                            break
                        if kind == "awaiting_human":
                            state, reason = TaskState.failed, "execution_failed"
                            break
                finally:
                    close = getattr(iterator, "aclose", None)
                    if close is not None:
                        await close()
                return state, reason

            execution = asyncio.create_task(consume())
            try:
                while not execution.done():
                    activity.heartbeat()
                    await asyncio.wait({execution}, timeout=10)
                terminal_state, terminal_reason = await execution
            except BaseException:
                execution.cancel()
                await asyncio.gather(execution, return_exceptions=True)
                raise
            await self._report(value.task_id, terminal_state, sequence, terminal_reason)
        except asyncio.CancelledError:
            await self._report(
                value.task_id, TaskState.cancelled, sequence, "cancelled"
            )
            raise
        except (StandingAuthorizationError, AuthorizationError):
            await self._report(
                value.task_id, TaskState.failed, sequence, "authority_lost"
            )
        except AgentRunRegistrationError:
            await self._report(
                value.task_id, TaskState.failed, sequence, "registration_failed"
            )
        except AgentRunDelegationUnavailableError:
            await self._report(
                value.task_id, TaskState.failed, sequence, "delegation_unavailable"
            )
        except Exception:
            await self._report(
                value.task_id, TaskState.failed, sequence, "execution_failed"
            )

    @activity.defn(name="fred.create_scheduled_agent_run_occurrence.v1")
    async def create_occurrence(
        self, value: tuple[ScheduledAgentRunInputV1, ScheduledAgentRunOccurrenceRequest]
    ) -> ScheduledAgentRunOccurrence:
        schedule, request = value
        return await self._reporter.create_occurrence(schedule.schedule_id, request)
