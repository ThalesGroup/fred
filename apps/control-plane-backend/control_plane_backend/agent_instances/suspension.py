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
- `SuspensionReason` — the three typed reasons
- `reconcile_instance_suspension(...)` — the availability reconciliation entry
  point (the proactive sweep's per-instance unit AND the documented trigger
  point #1980's ReBAC revocation calls, see below)
- `reconcile_instance_config_health(...)` — the config-invalid detection unit
  (a stored slice that no longer validates, incl. a failing `upgrade_config`)
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
from collections.abc import Collection
from enum import Enum
from typing import Protocol

from fred_core.common import TeamId
from fred_core.kpi.base_kpi_writer import BaseKPIWriter
from fred_core.kpi.kpi_writer_structures import KPIActor
from fred_sdk.contracts.capability.mcp_ids import is_mcp_capability_id

from control_plane_backend.agent_instances.store import (
    AgentInstanceRecord,
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
    """

    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    CAPABILITY_ACCESS_REVOKED = "capability_access_revoked"
    CAPABILITY_CONFIG_INVALID = "capability_config_invalid"


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
) -> list[str]:
    """
    The instance's selected NON-MCP capabilities the pod no longer advertises.

    MCP (`mcp:<id>`) selections are tolerated at agent assembly (the live tool
    provider skips unknown/disabled servers), mirroring the runtime's
    `_build_capability_block`, so a missing MCP server is a catalog warning —
    never a suspension. Real capabilities are the loud ones.
    """

    available = set(available_capability_ids)
    selected = instance.tuning.selected_capability_ids or []
    return [
        cap_id
        for cap_id in selected
        if not is_mcp_capability_id(cap_id) and cap_id not in available
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
    kpi_writer: BaseKPIWriter | None = None,
) -> AgentInstanceRecord | None:
    """
    Flip one instance to `suspended(reason)` and emit the log + metric.

    Idempotent: re-suspending with the same reason still rewrites the column but
    only the first transition into a reason is worth acting on; callers that
    care about "changed" should compare `instance.suspension_reason` first.
    """

    updated = await store.set_suspension(
        instance.agent_instance_id, instance.team_id, reason=reason.value
    )
    _emit_suspended(instance, reason, capabilities, kpi_writer)
    return updated


async def clear_suspension(
    store: SuspensionStore,
    instance: AgentInstanceRecord,
    *,
    kpi_writer: BaseKPIWriter | None = None,
) -> AgentInstanceRecord | None:
    """
    Clear any suspension on one instance. No-op (returns the instance) when it is
    not currently suspended.
    """

    previous = instance.suspension_reason
    if previous is None:
        return instance
    updated = await store.set_suspension(
        instance.agent_instance_id, instance.team_id, reason=None
    )
    _emit_cleared(instance, previous, kpi_writer)
    return updated


async def reconcile_instance_suspension(
    *,
    instance: AgentInstanceRecord,
    store: SuspensionStore,
    available_capability_ids: Collection[str],
    revoked_reason: SuspensionReason = SuspensionReason.CAPABILITY_UNAVAILABLE,
    kpi_writer: BaseKPIWriter | None = None,
) -> SuspensionReason | None:
    """
    Reconcile one instance's capability AVAILABILITY and suspend it when a
    selected capability is gone (#1975, RFC §3.9). THE named entry point.

    Behaviour:
    - if any selected non-MCP capability is absent from
      `available_capability_ids` → suspend with `revoked_reason` (unless already
      suspended for that exact reason) and return it. This is the same mismatch
      the pod raises `UnknownCapabilityError` for at assembly — reconciliation
      catches it first so the agent leaves the catalog before anyone hits it.
    - otherwise, if the instance is currently suspended for an availability
      reason, CLEAR it (the capability came back — reinstall / re-grant) and
      return None. A `capability_config_invalid` suspension is left untouched:
      only a successful save clears that (RFC §3.9).

    Returns the reason the instance is (now) availability-suspended for, or None.

    #1980 calls this on ReBAC enablement-tuple deletion with
    `revoked_reason=SuspensionReason.CAPABILITY_ACCESS_REVOKED` and the reduced
    available set (see the module docstring's trigger-point contract).
    """

    missing = unavailable_capabilities(instance, available_capability_ids)
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
    kpi_writer: BaseKPIWriter | None = None,
) -> SuspensionReason | None:
    """
    Detect a `capability_config_invalid` instance by re-validating each active,
    non-MCP stored config slice through the pod (#1975, RFC §3.9).

    `validate_slice(capability_id, config) -> Awaitable[None]` re-runs the pod's
    `validate-config` (which applies the lazy `upgrade_config` hook for a stored
    slice whose `schema_version` lags the installed capability) and must raise
    `SliceInvalid` when the slice no longer validates. The first invalid slice
    suspends the instance with `capability_config_invalid` and stops.

    Availability takes precedence: an instance already suspended for an
    availability reason is skipped (untick-and-save is the fix path there, and a
    missing capability cannot be config-validated anyway).
    """

    if instance.suspension_reason in _AVAILABILITY_REASON_VALUES:
        return None

    for cap_id in instance.tuning.selected_capability_ids or []:
        if is_mcp_capability_id(cap_id):
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
