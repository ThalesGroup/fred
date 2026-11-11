# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Bounded, restart-safe delivery of committed preparation intentions."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from control_plane_backend.models.base import utcnow
from control_plane_backend.models.capability_preparation_models import (
    CapabilityPreparationRow,
)

logger = logging.getLogger(__name__)
_BATCH_SIZE = 20
_DISPATCH_LEASE = timedelta(seconds=30)


@dataclass(frozen=True)
class Delivery:
    preparation_id: str
    workflow_id: str
    task_queue: str
    deadline_at: datetime
    claim_id: str
    dispatch_attempts: int
    worker_token: str


async def claim_due(
    sessions: async_sessionmaker[AsyncSession], *, limit: int = _BATCH_SIZE
) -> list[Delivery]:
    now = utcnow()
    claim_id = str(uuid4())
    async with sessions() as session:
        async with session.begin():
            rows = (
                (
                    await session.execute(
                        select(CapabilityPreparationRow)
                        .where(
                            CapabilityPreparationRow.is_current.is_(True),
                            or_(
                                CapabilityPreparationRow.state == "pending",
                                and_(
                                    CapabilityPreparationRow.state == "running",
                                    CapabilityPreparationRow.run_id.is_(None),
                                ),
                            ),
                            CapabilityPreparationRow.deadline_at > now,
                            CapabilityPreparationRow.delivery_due_at <= now,
                            or_(
                                CapabilityPreparationRow.dispatch_until.is_(None),
                                CapabilityPreparationRow.dispatch_until <= now,
                            ),
                            CapabilityPreparationRow.dispatch_attempts < 10,
                        )
                        .order_by(CapabilityPreparationRow.delivery_due_at)
                        .limit(limit)
                        .with_for_update(skip_locked=True)
                    )
                )
                .scalars()
                .all()
            )
            deliveries: list[Delivery] = []
            for row in rows:
                row.state = "running"
                row.dispatch_attempts += 1
                row.dispatch_owner = claim_id
                row.dispatch_until = now + _DISPATCH_LEASE
                deliveries.append(
                    Delivery(
                        preparation_id=row.id,
                        workflow_id=row.workflow_id,
                        task_queue=row.task_queue,
                        deadline_at=row.deadline_at,
                        claim_id=claim_id,
                        dispatch_attempts=row.dispatch_attempts,
                        worker_token=row.worker_token,
                    )
                )
    return deliveries


async def finish_delivery(
    sessions: async_sessionmaker[AsyncSession],
    delivery: Delivery,
    *,
    run_id: str | None,
    terminal_without_result: bool = False,
) -> None:
    async with sessions() as session:
        async with session.begin():
            row = await session.get(CapabilityPreparationRow, delivery.preparation_id)
            if (
                row is None
                or row.dispatch_owner != delivery.claim_id
                or not row.is_current
                or row.state != "running"
            ):
                return
            row.dispatch_owner = None
            row.dispatch_until = None
            if terminal_without_result:
                row.state = "failed"
                row.error_code = "worker_result_missing"
                row.completed_at = utcnow()
            elif run_id is not None:
                row.run_id = run_id
            elif row.dispatch_attempts >= 10:
                row.state = "failed"
                row.error_code = "dispatch_exhausted"
                row.completed_at = utcnow()
            else:
                delay = min(2**row.dispatch_attempts, 60)
                row.delivery_due_at = utcnow() + timedelta(seconds=delay)


async def fail_expired(
    sessions: async_sessionmaker[AsyncSession], *, limit: int = _BATCH_SIZE
) -> int:
    now = utcnow()
    async with sessions() as session:
        async with session.begin():
            rows = (
                (
                    await session.execute(
                        select(CapabilityPreparationRow)
                        .where(
                            CapabilityPreparationRow.is_current.is_(True),
                            CapabilityPreparationRow.state.in_(("pending", "running")),
                            CapabilityPreparationRow.deadline_at <= now,
                        )
                        .order_by(CapabilityPreparationRow.deadline_at)
                        .limit(limit)
                        .with_for_update(skip_locked=True)
                    )
                )
                .scalars()
                .all()
            )
            for row in rows:
                row.state = "failed"
                row.error_code = "preparation_deadline_exceeded"
                row.completed_at = now
                row.dispatch_owner = None
                row.dispatch_until = None
    return len(rows)


async def _deliver(
    client: Client, sessions: async_sessionmaker[AsyncSession], delivery: Delivery
) -> None:
    run_id: str | None = None
    terminal = False
    try:
        handle = await asyncio.wait_for(
            client.start_workflow(
                "CapabilityPreparationWorkflow",
                args=[delivery.preparation_id, delivery.worker_token],
                id=delivery.workflow_id,
                task_queue=delivery.task_queue,
                id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
                run_timeout=max(timedelta(seconds=1), delivery.deadline_at - utcnow()),
            ),
            timeout=10,
        )
        run_id = handle.run_id
    except (WorkflowAlreadyStartedError, RPCError) as exc:
        if isinstance(exc, RPCError) and exc.status != RPCStatusCode.ALREADY_EXISTS:
            logger.warning("Preparation delivery failed: %s", type(exc).__name__)
        else:
            try:
                description = await asyncio.wait_for(
                    client.get_workflow_handle(delivery.workflow_id).describe(),
                    timeout=10,
                )
                run_id = description.run_id
                terminal = (
                    description.status is not None
                    and description.status.name != "RUNNING"
                )
            except Exception as reconcile_error:
                logger.warning(
                    "Preparation delivery reconciliation failed: %s",
                    type(reconcile_error).__name__,
                )
    except Exception as exc:
        logger.warning("Preparation delivery interrupted: %s", type(exc).__name__)
    await finish_delivery(
        sessions, delivery, run_id=run_id, terminal_without_result=terminal
    )


async def dispatch_once(
    client: Client, sessions: async_sessionmaker[AsyncSession]
) -> int:
    await fail_expired(sessions)
    deliveries = await claim_due(sessions)
    semaphore = asyncio.Semaphore(5)

    async def bounded(delivery: Delivery) -> None:
        async with semaphore:
            await _deliver(client, sessions, delivery)

    await asyncio.gather(*(bounded(delivery) for delivery in deliveries))
    return len(deliveries)


async def run_dispatcher(
    client: Client,
    sessions: async_sessionmaker[AsyncSession],
    stop: asyncio.Event,
) -> None:
    while not stop.is_set():
        try:
            await dispatch_once(client, sessions)
        except Exception:
            logger.exception("Capability preparation dispatch pass failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=2)
        except TimeoutError:
            # The timeout starts the next dispatch cycle.
            pass
