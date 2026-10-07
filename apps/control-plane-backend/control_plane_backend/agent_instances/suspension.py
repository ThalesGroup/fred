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
Agent-instance suspension lifecycle (#1975, RFC AGENT-CAPABILITY §3.9).

Why this module exists:
- a broken capability must SUSPEND the agent, never silently degrade it — an
  agent missing its document-access tools would confidently answer from priors,
  and that trust failure is worse than unavailability (RFC §3.9)
- `suspended` is a platform-forced state DISTINCT from the editor's `enabled`
  toggle, carrying a typed reason (`SuspensionReason`)
- the #1971 spike proved LangGraph gives no assembly/run-time signal and that
  capability state survives a capability-less turn, so suspension is a pure
  control-plane product decision made here — not a checkpointer concern

What lives here:
- `SuspensionReason` — the typed reasons
- `reconcile_instance_suspension(...)` — the availability reconciliation entry
  point (the proactive sweep's per-instance unit AND the documented trigger
  point #1980's ReBAC revocation calls, see below)
- `reconcile_instance_config_health(...)` — the config-invalid detection unit
  (a stored slice that no longer validates, incl. a failing `upgrade_config`)
- `reconcile_instance_readiness(...)` — the `capability_pending` unit, fed by
  the pod's capability `readiness` verdicts
- `settle_readiness_after_save(...)` — the single suspension write after a
  save that re-validated its capability slices
- `suspend_instance` / `clear_suspension` — the store writes + observability

#1980 TRIGGER-POINT CONTRACT (ReBAC team scoping, sequenced AFTER #1975):
    When an enablement tuple is deleted, #1980 recomputes the set of capability
    ids the instance's team may still use, then calls
    `reconcile_instance_suspension(instance=..., store=...,
    available_capability_ids=<remaining>, revoked_reason=
    SuspensionReason.CAPABILITY_ACCESS_REVOKED, kpi_writer=...)`. #1975 does NOT
    perform any ReBAC check itself — it only exposes this entry point. The
    default `revoked_reason` (`CAPABILITY_UNAVAILABLE`) covers the
    manifest-change / pod-rollback path driven by the reconciliation sweep.
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from fred_core.common import TeamId
from fred_core.kpi.base_kpi_writer import BaseKPIWriter
from fred_core.kpi.kpi_writer_structures import KPIActor

from control_plane_backend.agent_instances.store import (
    ANY_REASON,
    AgentInstanceRecord,
    ExpectedReason,
)

logger = logging.getLogger(__name__)


class SuspensionStore(Protocol):
    """
    The narrow store surface the suspension lifecycle writes through (#1975).

    Structural so the real `AgentInstanceStore` and the unit-test fake both
    satisfy it without an inheritance coupling — the lifecycle only ever needs
    to set/clear one instance's suspension reason.
    """

    async def set_suspension(
        self,
        agent_instance_id: str,
        team_id: TeamId,
        *,
        reason: str | None,
        detail: str | None = None,
        expected_reason: ExpectedReason = ANY_REASON,
    ) -> AgentInstanceRecord | None: ...


class SuspensionReason(str, Enum):
    """
    Typed reason a managed agent instance is platform-suspended (RFC §3.9).

    - `capability_unavailable`: a selected capability is no longer advertised by
      the instance's pod (package removed, rollback).
    - `capability_access_revoked`: the team's ReBAC grant for a selected
      capability was revoked (#1980 wires this reason).
    - `capability_config_invalid`: a persisted `capability_config` slice no
      longer validates against the current `StoredConfigModel` and its lazy
      `upgrade_config` hook could not migrate it.
    - `capability_pending`: a capability's `readiness` hook reports its saved
      slice is still being prepared, or that preparing it failed (then
      `suspension_detail` carries the message). Set and cleared only from
      readiness verdicts (`reconcile_instance_readiness`, and
      `settle_readiness_after_save` after a save); the lowest-precedence reason.
    """

    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    CAPABILITY_ACCESS_REVOKED = "capability_access_revoked"
    CAPABILITY_CONFIG_INVALID = "capability_config_invalid"
    CAPABILITY_PENDING = "capability_pending"


# Reasons that an availability reconcile OWNS: it may both set and CLEAR them,
# because it can prove the capability is back by re-reading the pod's advertised
# manifests. `capability_config_invalid` is deliberately NOT here — only a
# successful save (which re-validates every ACTIVE slice) clears it, so no
# second clearing mechanism is introduced (RFC §3.9).
AVAILABILITY_REASONS: frozenset[SuspensionReason] = frozenset(
    {
        SuspensionReason.CAPABILITY_UNAVAILABLE,
        SuspensionReason.CAPABILITY_ACCESS_REVOKED,
    }
)

_AVAILABILITY_REASON_VALUES: frozenset[str] = frozenset(
    r.value for r in AVAILABILITY_REASONS
)

_KPI_ACTOR = KPIActor(type="system")
_SUSPENDED_METRIC = "agent.suspended_total"
_CLEARED_METRIC = "agent.suspension_cleared_total"


class SliceInvalid(Exception):
    """
    Raised by a `validate_slice` callable when a stored capability config slice
    no longer validates against the pod's current schema (RFC §3.9).

    Carries the capability id and the pod's plain-language message (the
    "reset its parameters and re-save the agent" wording), so callers can
    surface it verbatim.
    """

    def __init__(self, capability_id: str, message: str) -> None:
        super().__init__(message)
        self.capability_id = capability_id
        self.message = message


def unavailable_capabilities(
    instance: AgentInstanceRecord,
    available_capability_ids: Collection[str],
    *,
    tolerated_ids: Collection[str] = (),
) -> list[str]:
    """
    The instance's selected capabilities the pod no longer advertises (#1988).

    Every capability id is FGA-safe and reconciled the same way now — an
    MCP-backed capability's id is the plain catalog server id, no longer a
    `mcp:<id>` id skipped wholesale.

    `tolerated_ids` names capabilities that must never be reported unavailable
    even when absent from `available_capability_ids`. It is used ONLY by the
    availability sweep to carry the pod's known-but-DISABLED catalog MCP servers
    (supplied from the pod MCP catalog): such a server is intentionally skipped
    by the live tool provider at assembly, so a missing tool is a catalog
    warning — never a suspension. The revocation path passes nothing here, so
    revoking an MCP-backed capability DOES suspend its dependents.
    """

    available = set(available_capability_ids)
    tolerated = set(tolerated_ids)
    selected = instance.tuning.selected_capability_ids or []
    return [
        cap_id
        for cap_id in selected
        if cap_id not in available and cap_id not in tolerated
    ]


def _emit_suspended(
    instance: AgentInstanceRecord,
    reason: SuspensionReason,
    capabilities: Collection[str],
    kpi_writer: BaseKPIWriter | None,
) -> None:
    """Structured log + counter metric per suspension (RFC §3.9 observability)."""

    logger.warning(
        "[capability-suspension] suspended instance=%s team=%s reason=%s "
        "capabilities=%s",
        instance.agent_instance_id,
        instance.team_id,
        reason.value,
        sorted(capabilities),
    )
    if kpi_writer is not None:
        kpi_writer.count(
            _SUSPENDED_METRIC,
            dims={
                "team_id": str(instance.team_id),
                "agent_instance_id": instance.agent_instance_id,
                "reason": reason.value,
            },
            actor=_KPI_ACTOR,
        )


def _emit_cleared(
    instance: AgentInstanceRecord,
    previous_reason: str,
    kpi_writer: BaseKPIWriter | None,
) -> None:
    logger.info(
        "[capability-suspension] cleared instance=%s team=%s previous_reason=%s",
        instance.agent_instance_id,
        instance.team_id,
        previous_reason,
    )
    if kpi_writer is not None:
        kpi_writer.count(
            _CLEARED_METRIC,
            dims={
                "team_id": str(instance.team_id),
                "agent_instance_id": instance.agent_instance_id,
                "reason": previous_reason,
            },
            actor=_KPI_ACTOR,
        )


async def suspend_instance(
    store: SuspensionStore,
    instance: AgentInstanceRecord,
    reason: SuspensionReason,
    *,
    capabilities: Collection[str] = (),
    detail: str | None = None,
    kpi_writer: BaseKPIWriter | None = None,
    conditional: bool = False,
) -> AgentInstanceRecord | None:
    """
    Flip one instance to `suspended(reason)` and emit the log + metric.

    Idempotent: re-suspending with the same reason still rewrites the column but
    only the first transition into a reason is worth acting on; callers that
    care about "changed" should compare `instance.suspension_reason` first.
    `conditional=True` writes only while the row still holds the reason read
    into `instance`, so a concurrent suspension is never overwritten.
    """

    updated = await store.set_suspension(
        instance.agent_instance_id,
        instance.team_id,
        reason=reason.value,
        detail=detail,
        expected_reason=instance.suspension_reason if conditional else ANY_REASON,
    )
    if updated is None or updated.suspension_reason == reason.value:
        _emit_suspended(instance, reason, capabilities, kpi_writer)
    return updated


async def clear_suspension(
    store: SuspensionStore,
    instance: AgentInstanceRecord,
    *,
    kpi_writer: BaseKPIWriter | None = None,
    conditional: bool = False,
) -> AgentInstanceRecord | None:
    """
    Clear any suspension on one instance. No-op (returns the instance) when it is
    not currently suspended. `conditional=True` clears only while the row still
    holds the reason read into `instance`.
    """

    previous = instance.suspension_reason
    if previous is None:
        return instance
    updated = await store.set_suspension(
        instance.agent_instance_id,
        instance.team_id,
        reason=None,
        expected_reason=previous if conditional else ANY_REASON,
    )
    if updated is None or updated.suspension_reason is None:
        _emit_cleared(instance, previous, kpi_writer)
    return updated


async def reconcile_instance_suspension(
    *,
    instance: AgentInstanceRecord,
    store: SuspensionStore,
    available_capability_ids: Collection[str],
    tolerated_ids: Collection[str] = (),
    revoked_reason: SuspensionReason = SuspensionReason.CAPABILITY_UNAVAILABLE,
    kpi_writer: BaseKPIWriter | None = None,
) -> SuspensionReason | None:
    """
    Reconcile one instance's capability AVAILABILITY and suspend it when a
    selected capability is gone (#1975, RFC §3.9). THE named entry point.

    Behaviour:
    - if any selected capability is absent from `available_capability_ids` (and
      not in `tolerated_ids`) → suspend with `revoked_reason` (unless already
      suspended for that exact reason) and return it. This is the same mismatch
      the pod raises `UnknownCapabilityError` for at assembly — reconciliation
      catches it first so the agent leaves the catalog before anyone hits it.
    - otherwise, if the instance is currently suspended for an availability
      reason, CLEAR it (the capability came back — reinstall / re-grant) and
      return None. A `capability_config_invalid` suspension is left untouched:
      only a successful save clears that (RFC §3.9).

    Returns the reason the instance is (now) availability-suspended for, or None.

    `tolerated_ids` (#1988) carries the known-but-disabled catalog MCP servers
    the availability sweep supplies from the pod MCP catalog; those are never
    reported unavailable. The revocation path passes nothing so revoking an
    MCP-backed capability suspends its dependents.

    #1980 calls this on ReBAC enablement-tuple deletion with
    `revoked_reason=SuspensionReason.CAPABILITY_ACCESS_REVOKED` and the reduced
    available set (see the module docstring's trigger-point contract).
    """

    missing = unavailable_capabilities(
        instance, available_capability_ids, tolerated_ids=tolerated_ids
    )
    current = instance.suspension_reason
    if missing:
        if current != revoked_reason.value:
            await suspend_instance(
                store,
                instance,
                revoked_reason,
                capabilities=missing,
                kpi_writer=kpi_writer,
            )
        return revoked_reason
    if current in _AVAILABILITY_REASON_VALUES:
        await clear_suspension(store, instance, kpi_writer=kpi_writer)
    return None


async def reconcile_instance_config_health(
    *,
    instance: AgentInstanceRecord,
    store: SuspensionStore,
    validate_slice,
    skip_ids: Collection[str] = (),
    kpi_writer: BaseKPIWriter | None = None,
) -> SuspensionReason | None:
    """
    Detect a `capability_config_invalid` instance by re-validating each active
    stored config slice through the pod (#1975, RFC §3.9).

    `validate_slice(capability_id, config) -> Awaitable[None]` re-runs the pod's
    `validate-config` (which applies the lazy `upgrade_config` hook for a stored
    slice whose `schema_version` lags the installed capability) and must raise
    `SliceInvalid` when the slice no longer validates. The first invalid slice
    suspends the instance with `capability_config_invalid` and stops.

    `skip_ids` (#1988) names capabilities NOT to pod-revalidate — the caller
    passes the pod's MCP catalog server ids so MCP-backed config slices keep
    today's behaviour (not pod-revalidated). A DISABLED catalog server's
    capability is absent from the pod registry, so revalidating it would falsely
    suspend.

    Availability takes precedence: an instance already suspended for an
    availability reason is skipped (untick-and-save is the fix path there, and a
    missing capability cannot be config-validated anyway).
    """

    if instance.suspension_reason in _AVAILABILITY_REASON_VALUES:
        return None

    skip = set(skip_ids)
    for cap_id in instance.tuning.selected_capability_ids or []:
        if cap_id in skip:
            continue
        stored = instance.tuning.capability_config.get(cap_id)
        config = dict(stored.get("config") or {}) if isinstance(stored, dict) else {}
        try:
            await validate_slice(cap_id, config)
        except SliceInvalid:
            if (
                instance.suspension_reason
                != SuspensionReason.CAPABILITY_CONFIG_INVALID.value
            ):
                await suspend_instance(
                    store,
                    instance,
                    SuspensionReason.CAPABILITY_CONFIG_INVALID,
                    capabilities=[cap_id],
                    kpi_writer=kpi_writer,
                )
            return SuspensionReason.CAPABILITY_CONFIG_INVALID

    # Every active slice validates. A config-invalid suspension is cleared ONLY
    # by a successful save (RFC §3.9), never here — so if the instance is still
    # marked config-invalid we REPORT it as such (the caller must not treat this
    # as "cleared"); otherwise it is healthy.
    if instance.suspension_reason == SuspensionReason.CAPABILITY_CONFIG_INVALID.value:
        return SuspensionReason.CAPABILITY_CONFIG_INVALID
    return None


@dataclass(frozen=True)
class ReadinessVerdict:
    """The pod's aggregated `readiness` answer for one instance: `ready`, or
    not ready with the failure message when a capability reported one."""

    ready: bool
    capability_ids: tuple[str, ...] = ()
    detail: str | None = None


def aggregate_readiness(results: Collection[Mapping[str, object]]) -> ReadinessVerdict:
    """Fold per-capability pod results into one verdict; a failure outranks a
    pending capability so its message reaches the editor."""

    not_ready = [r for r in results if r.get("state") in ("pending", "failed")]
    if not not_ready:
        return ReadinessVerdict(ready=True)
    failed = next((r for r in not_ready if r.get("state") == "failed"), None)
    detail = failed.get("detail") if failed is not None else None
    return ReadinessVerdict(
        ready=False,
        capability_ids=tuple(str(r.get("capability_id")) for r in not_ready),
        detail=str(detail) if detail else None,
    )


async def reconcile_instance_readiness(
    *,
    instance: AgentInstanceRecord,
    store: SuspensionStore,
    verdict: ReadinessVerdict | None,
    kpi_writer: BaseKPIWriter | None = None,
) -> SuspensionReason | None:
    """
    Set, refresh or clear `capability_pending` from one readiness verdict.

    Any other reason outranks it and is left untouched. `verdict=None` (pod
    unreachable, no answer) changes nothing. Writes are compare-and-set on the
    reason read into `instance`: the pod call before them can take seconds.
    Returns the instance's pending reason after the call, or None.
    """

    current = instance.suspension_reason
    pending = SuspensionReason.CAPABILITY_PENDING
    if current is not None and current != pending.value:
        return None
    if verdict is None:
        return pending if current == pending.value else None
    if verdict.ready:
        if current != pending.value:
            return None
        updated = await clear_suspension(
            store, instance, kpi_writer=kpi_writer, conditional=True
        )
    elif current != pending.value or instance.suspension_detail != verdict.detail:
        updated = await suspend_instance(
            store,
            instance,
            pending,
            capabilities=verdict.capability_ids,
            detail=verdict.detail,
            kpi_writer=kpi_writer,
            conditional=True,
        )
    else:
        return pending
    reason = updated.suspension_reason if updated is not None else None
    return pending if reason == pending.value else None


async def settle_readiness_after_save(
    *,
    instance: AgentInstanceRecord,
    store: SuspensionStore,
    verdict: ReadinessVerdict | None,
    kpi_writer: BaseKPIWriter | None = None,
) -> AgentInstanceRecord | None:
    """
    Write the one suspension state a save that re-validated its capability
    slices leads to: `capability_pending` unless the pod answered ready, else
    none. The save resolves any earlier reason, and no verdict fails closed:
    the listing re-check or the sweep lifts it once the pod answers.
    """

    if verdict is not None and verdict.ready:
        return await clear_suspension(
            store, instance, kpi_writer=kpi_writer, conditional=True
        )
    pending = SuspensionReason.CAPABILITY_PENDING
    detail = verdict.detail if verdict is not None else None
    if (
        instance.suspension_reason == pending.value
        and instance.suspension_detail == detail
    ):
        return instance
    return await suspend_instance(
        store,
        instance,
        pending,
        capabilities=verdict.capability_ids if verdict is not None else (),
        detail=detail,
        kpi_writer=kpi_writer,
        conditional=True,
    )
