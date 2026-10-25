# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""PostgreSQL-backed admission and conversation leases for SIG sandboxes."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import random
from contextlib import suppress
from dataclasses import dataclass
from secrets import token_hex
from time import monotonic

import asyncpg
from fred_sdk.contracts.sandbox import SandboxError, SandboxRequest, SandboxResult

from .agent_sandbox_backend import AgentSandboxBackend
from .backend import SandboxLease
from .config import BrokerSettings
from .mounts import revoke_view, view_key_for_mount

logger = logging.getLogger(__name__)
_CAPACITY_LOCK = 748142927
_OWNER_SECONDS = 45
_HEARTBEAT_SECONDS = 10
_SWEEP_SECONDS = 10
_ACTIVE_STATES = ("preparing", "running", "suspending", "resuming", "deleting")


@dataclass(frozen=True, slots=True)
class _SessionRow:
    session_key: str
    tenant_key: str
    workspace_id: str
    view_epoch: str
    state: str
    resource_name: str | None
    owner_token: str | None
    expired: bool


class SharedConversationPool:
    def __init__(self, backend: AgentSandboxBackend, settings: BrokerSettings) -> None:
        self.backend = backend
        self.settings = settings
        self._database: asyncpg.Pool | None = None
        self._worker: asyncio.Task[None] | None = None
        self._prepare_count = 0
        self._prepare_seconds = 0.0
        self._admission_refusals = 0

    async def start(self) -> None:
        await self.backend.preflight()
        try:
            self._database = await asyncpg.create_pool(
                self.settings.coordinator_dsn,
                min_size=1,
                max_size=20,
                command_timeout=10,
            )
            async with self._database.acquire() as connection:
                await connection.fetchval(
                    "SELECT count(*) FROM sandbox_conversation_leases"
                )
                await connection.fetchval(
                    "SELECT max_active_sessions FROM sandbox_settings WHERE id='default'"
                )
        except Exception as exc:
            if self._database is not None:
                await self._database.close()
                self._database = None
            raise SandboxError("unavailable") from exc
        self._worker = asyncio.create_task(self._sweep_loop())

    async def close(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            with suppress(asyncio.CancelledError):
                await self._worker
        if self._database is not None:
            await self._database.close()

    def _active_idle_seconds(self, idle_seconds: int) -> int:
        return min(self.settings.active_idle_seconds, max(1, idle_seconds - 1))

    async def view_key(self, key: str, tenant: str) -> str:
        row = await self._ensure(key, tenant)
        if row.expired:
            await self._expire(key, tenant)
            row = await self._ensure(key, tenant)
            if row.expired:
                raise SandboxError("busy")
        return self._view_key(row)

    async def execute(
        self, key: str, tenant: str, request: SandboxRequest
    ) -> SandboxResult:
        deadline = monotonic() + self.settings.queue_wait_seconds
        ticket: str | None = None
        owner = token_hex(16)
        row: _SessionRow | None = None
        attempts = 0
        try:
            while monotonic() < deadline:
                row = await self._ensure(key, tenant)
                if row.expired:
                    await self._expire(key, tenant)
                    await asyncio.sleep(0.2)
                    continue
                admitted, ticket, previous_state = await self._reserve(
                    row, owner, ticket
                )
                if admitted:
                    break
                attempts += 1
                await asyncio.sleep(
                    min(1.5, 0.1 * 2 ** min(attempts, 4)) + random.uniform(0, 0.1)
                )
            else:
                self._admission_refusals += 1
                raise SandboxError("busy")
            assert row is not None
            name = row.resource_name or f"fred-sbx-{row.workspace_id[:20]}"
            view = self._view_key(row)
            lease: SandboxLease | None = None
            work = asyncio.current_task()
            heartbeat = asyncio.create_task(self._heartbeat(key, owner, work))
            try:
                preparation_started = monotonic()
                if previous_state in {"new", "preparing"}:
                    if previous_state == "preparing":
                        await self.backend.dispose(
                            SandboxLease(name, name, view_key_for_mount(view))
                        )
                    lease = await self.backend.prepare(view, name=name)
                elif previous_state in {"suspended", "resuming", "suspending"}:
                    await self.backend.preflight()
                    lease = await self.backend.resume(name, view_key_for_mount(view))
                else:
                    await self.backend.preflight()
                    lease = await self.backend.attach(name, view_key_for_mount(view))
                if previous_state not in {"new", "preparing"}:
                    from .process_cleanup import remove_code_processes

                    await remove_code_processes(
                        self.backend.runner,
                        self.backend.kubernetes._kubectl("exec", lease.target, "--"),
                    )
                self._prepare_count += 1
                self._prepare_seconds += monotonic() - preparation_started
                await self._mark_running(key, owner, name)
                idle_seconds, _ = await self._policy(self._db())
                await self.backend.renew(
                    lease,
                    idle_seconds + self.settings.execution_timeout_seconds + 30,
                )
                result = await asyncio.wait_for(
                    self.backend.execute(lease, request),
                    timeout=self.settings.execution_timeout_seconds + 3,
                )
                if result.timed_out:
                    await self._dispose(key, owner, name, view)
                else:
                    idle_seconds, _ = await self._policy(self._db())
                    await self.backend.renew(lease, idle_seconds)
                    await self._finish(key, owner)
                return result
            except BaseException as exc:
                if isinstance(exc, SandboxError) and exc.code == "policy_unavailable":
                    with suppress(Exception):
                        await self._dispose(key, owner, name, view)
                elif lease is not None and not isinstance(exc, asyncio.CancelledError):
                    try:
                        await self.backend.suspend(name)
                        await self._mark_suspended(key, owner)
                    except Exception:
                        logger.exception("Unable to suspend failed sandbox execution")
                raise
            finally:
                heartbeat.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat
        except asyncpg.PostgresError as exc:
            raise SandboxError("unavailable") from exc
        finally:
            if ticket is not None:
                await self._remove_ticket(ticket)

    async def _ensure(self, key: str, tenant: str) -> _SessionRow:
        database = self._db()
        try:
            async with database.acquire() as connection:
                async with connection.transaction():
                    existing = await connection.fetchrow(
                        "SELECT tenant_key FROM sandbox_conversation_leases WHERE session_key=$1",
                        key,
                    )
                    if existing is None:
                        await connection.execute(
                            "SELECT pg_advisory_xact_lock($1)", _CAPACITY_LOCK
                        )
                        if (
                            await connection.fetchval(
                                "SELECT count(*) FROM sandbox_conversation_leases"
                            )
                            >= self.settings.max_retained_sessions
                        ):
                            raise SandboxError("busy")
                        await connection.execute(
                            """INSERT INTO sandbox_conversation_leases
                               (session_key, tenant_key, workspace_id, view_epoch, state,
                                created_at, last_used_at, updated_at)
                               VALUES ($1,$2,$3,$4,'new',now(),now(),now())
                               ON CONFLICT (session_key) DO NOTHING""",
                            key,
                            tenant,
                            token_hex(16),
                            token_hex(16),
                        )
                    data = await connection.fetchrow(
                        """SELECT *, last_used_at < now() - ($2 * interval '1 second') AS expired
                           FROM sandbox_conversation_leases WHERE session_key=$1""",
                        key,
                        (await self._policy(connection))[0],
                    )
                    if data is None or data["tenant_key"] != tenant:
                        raise SandboxError("unauthorized")
                    return _SessionRow(
                        key,
                        tenant,
                        data["workspace_id"],
                        data["view_epoch"],
                        data["state"],
                        data["resource_name"],
                        data["owner_token"],
                        data["expired"],
                    )
        except (OSError, asyncpg.PostgresError) as exc:
            raise SandboxError("unavailable") from exc

    async def _reserve(
        self, row: _SessionRow, owner: str, ticket: str | None
    ) -> tuple[bool, str | None, str]:
        try:
            async with self._db().acquire() as connection:
                async with connection.transaction():
                    await connection.execute(
                        "SELECT pg_advisory_xact_lock($1)", _CAPACITY_LOCK
                    )
                    await connection.execute(
                        "DELETE FROM sandbox_wait_tickets WHERE expires_at < now()"
                    )
                    current = await connection.fetchrow(
                        """SELECT state, owner_token, owner_expires_at,
                           tenant_key, view_epoch, last_used_at
                           FROM sandbox_conversation_leases
                           WHERE session_key=$1 FOR UPDATE""",
                        row.session_key,
                    )
                    if current is None:
                        return False, ticket, current["state"] if current else "new"
                    if (
                        current["tenant_key"] != row.tenant_key
                        or current["view_epoch"] != row.view_epoch
                    ):
                        return False, ticket, current["state"]
                    if (
                        current["owner_token"]
                        and current["owner_expires_at"]
                        and current["owner_expires_at"]
                        > await connection.fetchval("SELECT now()")
                    ):
                        return False, ticket, current["state"]
                    if current["state"] not in _ACTIVE_STATES:
                        active = await connection.fetchval(
                            """SELECT count(*) FROM sandbox_conversation_leases
                               WHERE state = ANY($1::text[])""",
                            list(_ACTIVE_STATES),
                        )
                        preparing = await connection.fetchval(
                            """SELECT count(*) FROM sandbox_conversation_leases
                               WHERE state IN ('preparing','resuming')"""
                        )
                        _, limit = await self._policy(connection)
                        first = await connection.fetchval(
                            """SELECT t.id FROM sandbox_wait_tickets t
                               JOIN sandbox_conversation_leases s
                                 ON s.session_key=t.session_key
                               WHERE s.owner_token IS NULL OR s.owner_expires_at < now()
                               ORDER BY t.created_at, t.id LIMIT 1"""
                        )
                        if (
                            active >= limit
                            or preparing >= self.settings.max_preparations
                            or (first is not None and first != ticket)
                        ):
                            if ticket is None:
                                total = await connection.fetchval(
                                    "SELECT count(*) FROM sandbox_wait_tickets"
                                )
                                tenant_total = await connection.fetchval(
                                    "SELECT count(*) FROM sandbox_wait_tickets WHERE tenant_key=$1",
                                    row.tenant_key,
                                )
                                if (
                                    total >= self.settings.max_queue_length
                                    or tenant_total
                                    >= self.settings.max_queue_per_tenant
                                ):
                                    raise SandboxError("busy")
                                ticket = token_hex(16)
                                await connection.execute(
                                    """INSERT INTO sandbox_wait_tickets
                                       (id,session_key,tenant_key,created_at,expires_at)
                                       VALUES ($1,$2,$3,now(),now()+($4 * interval '1 second'))""",
                                    ticket,
                                    row.session_key,
                                    row.tenant_key,
                                    self.settings.queue_wait_seconds,
                                )
                            return False, ticket, current["state"]
                    new_state = {
                        "new": "preparing",
                        "preparing": "preparing",
                        "suspended": "resuming",
                        "suspending": "resuming",
                        "resuming": "resuming",
                        "running": "running",
                    }.get(current["state"])
                    if new_state is None:
                        return False, ticket, current["state"]
                    await connection.execute(
                        """UPDATE sandbox_conversation_leases SET state=$2,
                           resource_name=COALESCE(resource_name,$3), owner_token=$4,
                           owner_expires_at=now()+($5 * interval '1 second'),
                           updated_at=now() WHERE session_key=$1""",
                        row.session_key,
                        new_state,
                        row.resource_name or f"fred-sbx-{row.workspace_id[:20]}",
                        owner,
                        _OWNER_SECONDS,
                    )
                    if ticket:
                        await connection.execute(
                            "DELETE FROM sandbox_wait_tickets WHERE id=$1", ticket
                        )
                    return True, None, current["state"]
        except (OSError, asyncpg.PostgresError) as exc:
            raise SandboxError("unavailable") from exc

    async def _heartbeat(
        self, key: str, owner: str, work: asyncio.Task[object] | None
    ) -> None:
        while True:
            await asyncio.sleep(_HEARTBEAT_SECONDS)
            try:
                status = await self._db().execute(
                    """UPDATE sandbox_conversation_leases SET
                       owner_expires_at=now()+($3 * interval '1 second')
                       WHERE session_key=$1 AND owner_token=$2""",
                    key,
                    owner,
                    _OWNER_SECONDS,
                )
                if status != "UPDATE 1":
                    raise SandboxError("unavailable")
            except Exception:
                if work is not None:
                    work.cancel()
                return

    async def _mark_running(self, key: str, owner: str, name: str) -> None:
        status = await self._db().execute(
            """UPDATE sandbox_conversation_leases SET state='running',
               resource_name=$3, updated_at=now()
               WHERE session_key=$1 AND owner_token=$2""",
            key,
            owner,
            name,
        )
        if status != "UPDATE 1":
            raise SandboxError("unavailable")

    async def _finish(self, key: str, owner: str) -> None:
        status = await self._db().execute(
            """UPDATE sandbox_conversation_leases SET last_used_at=now(),
               updated_at=now(), owner_token=NULL, owner_expires_at=NULL
               WHERE session_key=$1 AND owner_token=$2""",
            key,
            owner,
        )
        if status != "UPDATE 1":
            raise SandboxError("unavailable")

    async def _mark_suspended(self, key: str, owner: str) -> None:
        status = await self._db().execute(
            """UPDATE sandbox_conversation_leases SET state='suspended',
               owner_token=NULL, owner_expires_at=NULL, updated_at=now()
               WHERE session_key=$1 AND owner_token=$2""",
            key,
            owner,
        )
        if status != "UPDATE 1":
            raise SandboxError("unavailable")

    async def _dispose(self, key: str, owner: str, name: str, view: str) -> None:
        status = await self._db().execute(
            """UPDATE sandbox_conversation_leases SET state='deleting',
               updated_at=now() WHERE session_key=$1 AND owner_token=$2""",
            key,
            owner,
        )
        if status != "UPDATE 1":
            raise SandboxError("unavailable")
        await self.backend.dispose(SandboxLease(name, name, view_key_for_mount(view)))
        if self.settings.mount_provider != "none":
            await revoke_view(self.settings, view_key_for_mount(view))
        await self._db().execute(
            "DELETE FROM sandbox_conversation_leases WHERE session_key=$1 AND owner_token=$2",
            key,
            owner,
        )

    async def _expire(self, key: str, tenant: str) -> None:
        row = await self._ensure(key, tenant)
        if not row.expired:
            return
        await self._sweep_one(row, delete=True)

    async def sweep(self) -> None:
        try:
            idle_seconds, _ = await self._policy(self._db())
            rows = await self._db().fetch(
                """SELECT session_key, tenant_key, workspace_id, view_epoch,
                   state, resource_name, owner_token,
                   last_used_at < now() - ($1 * interval '1 second') AS expired,
                   last_used_at < now() - ($2 * interval '1 second') AS inactive
                   FROM sandbox_conversation_leases
                   WHERE (owner_token IS NULL OR owner_expires_at < now())
                   AND (
                     state='deleting'
                     OR last_used_at < now() - ($1 * interval '1 second')
                     OR (state IN ('preparing','running','suspending','resuming')
                         AND last_used_at < now() - ($2 * interval '1 second'))
                   )
                   ORDER BY CASE WHEN state='deleting' OR
                     last_used_at < now() - ($1 * interval '1 second')
                     THEN 0 ELSE 1 END, last_used_at LIMIT 100""",
                idle_seconds,
                self._active_idle_seconds(idle_seconds),
            )
            for data in rows:
                if (
                    data["state"] != "deleting"
                    and not data["expired"]
                    and not data["inactive"]
                ):
                    continue
                row = _SessionRow(
                    data["session_key"],
                    data["tenant_key"],
                    data["workspace_id"],
                    data["view_epoch"],
                    data["state"],
                    data["resource_name"],
                    data["owner_token"],
                    data["expired"],
                )
                await self._sweep_one(
                    row, delete=data["expired"] or row.state == "deleting"
                )
        except Exception:
            logger.exception("Shared sandbox sweep failed")

    async def _sweep_one(self, row: _SessionRow, *, delete: bool) -> None:
        owner = token_hex(16)
        name = row.resource_name or f"fred-sbx-{row.workspace_id[:20]}"
        if not delete and row.state in {"new", "suspended"}:
            return
        try:
            idle_seconds, _ = await self._policy(self._db())
            status = await self._db().execute(
                """UPDATE sandbox_conversation_leases SET owner_token=$2,
                   owner_expires_at=now()+($3 * interval '1 second'),
                   state=CASE WHEN $4 THEN 'deleting' ELSE 'suspending' END,
                   updated_at=now() WHERE session_key=$1
                   AND workspace_id=$7 AND view_epoch=$8
                   AND (owner_token IS NULL OR owner_expires_at < now())
                   AND (($6 AND state='deleting') OR
                        last_used_at < now() - ($5 * interval '1 second'))""",
                row.session_key,
                owner,
                _OWNER_SECONDS,
                delete,
                idle_seconds if delete else self._active_idle_seconds(idle_seconds),
                row.state == "deleting",
                row.workspace_id,
                row.view_epoch,
            )
            if status != "UPDATE 1":
                return
            if delete:
                await self._dispose(row.session_key, owner, name, self._view_key(row))
            elif row.state == "preparing":
                await self._dispose(row.session_key, owner, name, self._view_key(row))
            elif row.state in {"running", "resuming", "suspending"}:
                await self.backend.suspend(name)
                await self._db().execute(
                    """UPDATE sandbox_conversation_leases SET state='suspended',
                       owner_token=NULL, owner_expires_at=NULL, updated_at=now()
                       WHERE session_key=$1 AND owner_token=$2""",
                    row.session_key,
                    owner,
                )
            else:
                await self._db().execute(
                    """UPDATE sandbox_conversation_leases SET owner_token=NULL,
                       owner_expires_at=NULL, state=$3
                       WHERE session_key=$1 AND owner_token=$2""",
                    row.session_key,
                    owner,
                    row.state,
                )
        except Exception:
            logger.exception("Unable to retire shared sandbox session")

    async def _sweep_loop(self) -> None:
        while True:
            await asyncio.sleep(_SWEEP_SECONDS)
            await self.sweep()

    async def _remove_ticket(self, ticket: str) -> None:
        with suppress(Exception):
            await self._db().execute(
                "DELETE FROM sandbox_wait_tickets WHERE id=$1", ticket
            )

    def _view_key(self, row: _SessionRow) -> str:
        return hmac.new(
            self.settings.token.encode(),
            b"fred-sandbox-view-v2\0"
            + row.session_key.encode()
            + b"\0"
            + row.view_epoch.encode(),
            hashlib.sha256,
        ).hexdigest()

    def _db(self) -> asyncpg.Pool:
        if self._database is None:
            raise SandboxError("unavailable")
        return self._database

    async def _policy(
        self, connection: asyncpg.Connection | asyncpg.Pool
    ) -> tuple[int, int]:
        row = await connection.fetchrow(
            "SELECT idle_minutes, max_active_sessions FROM sandbox_settings WHERE id='default'"
        )
        if row is None:
            return 1200, min(self.settings.max_sandboxes, 8)
        return row["idle_minutes"] * 60, min(
            self.settings.max_sandboxes, row["max_active_sessions"]
        )

    async def statistics(self) -> dict[str, int]:
        row = await self._db().fetchrow(
            """SELECT
                 count(*) FILTER (WHERE state = ANY($1::text[])) AS allocated,
                 count(*) FILTER (WHERE state = 'suspended') AS suspended,
                 count(*) FILTER (WHERE state IN ('preparing','resuming')) AS preparing,
                 count(*) AS retained
               FROM sandbox_conversation_leases""",
            list(_ACTIVE_STATES),
        )
        waiting = await self._db().fetchval(
            "SELECT count(*) FROM sandbox_wait_tickets WHERE expires_at >= now()"
        )
        idle_seconds, limit = await self._policy(self._db())
        assert row is not None
        return {
            "allocated": row["allocated"],
            "suspended": row["suspended"],
            "preparing": row["preparing"],
            "retained": row["retained"],
            "waiting": waiting,
            "limit": limit,
            "idle_timeout_seconds": idle_seconds,
        }

    async def prometheus(self) -> str:
        data = await self.statistics()
        lines = [f"fred_sandbox_{name} {value}" for name, value in data.items()]
        lines.extend(
            [
                f"fred_sandbox_prepare_count {self._prepare_count}",
                f"fred_sandbox_prepare_seconds_sum {self._prepare_seconds}",
                f"fred_sandbox_admission_refusals_total {self._admission_refusals}",
            ]
        )
        return "\n".join(lines) + "\n"
