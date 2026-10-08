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
Copy an agent to other teams or the personal space, and duplicate it in place.

The control plane only orchestrates: each capability's pod prepares its own
config for the destination (`copy-config`), resetting scope-private settings
and recreating configuration files. Acceptance:
openspec/changes/copy-agent-across-teams/.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx
from fastapi import HTTPException
from fred_core import (
    PLATFORM_ID,
    KeycloakUser,
    PlatformPermission,
    TeamPermission,
)
from fred_core.common import TeamId
from fred_core.logs.audit_log import emit_audit_log
from fred_core.security.rebac.rebac_engine import RebacDisabledResult
from fred_sdk.contracts.capability import CapabilityConfigCopyRequest

from control_plane_backend.agent_instances.store import AgentInstanceRecord
from control_plane_backend.capabilities.authz import usable_capability_ids
from control_plane_backend.product import service as product_service
from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.product.schemas import (
    AgentCopyCapability,
    AgentCopyNotice,
    AgentCopyResult,
    AgentCopyTarget,
)
from control_plane_backend.product.service import (
    EnrollmentError,
    _record_to_summary,
    capability_gate_exempt,
    emit_agent_created_kpi,
    template_capability_id,
)
from control_plane_backend.teams.system import resolve_system_team_id

logger = logging.getLogger(__name__)

# Destinations are prepared concurrently, each one calling the pod once per
# capability; keep the fan-out small.
_MAX_CONCURRENT_DESTINATIONS = 4
_IMPORTED_NAME_BASE_MAX = 230

TeamAccess = Callable[[TeamId], Awaitable[TeamId]]


def _runtime_base_url(
    record: AgentInstanceRecord, deps: ProductServiceDependencies
) -> str:
    source = next(
        (
            s
            for s in deps.configuration.platform.runtime_catalog_sources
            if s.runtime_id == record.source_runtime_id and s.enabled
        ),
        None,
    )
    if source is None:
        raise EnrollmentError(
            f"Runtime source {record.source_runtime_id!r} is not available or "
            "not enabled; the agent cannot be copied.",
            http_status=503,
        )
    return source.base_url


def _template_enabled(record: AgentInstanceRecord, usable: set[str] | None) -> bool:
    if usable is None or capability_gate_exempt(record.source_agent_id):
        return True
    return (
        template_capability_id(record.source_runtime_id, record.source_agent_id)
        in usable
    )


@dataclass(frozen=True)
class _CopySource:
    """What every destination of one copy request shares."""

    base_url: str
    capability_ids: list[str]
    names: dict[str, str]


async def _resolve_copy_source(
    user: KeycloakUser, record: AgentInstanceRecord, deps: ProductServiceDependencies
) -> _CopySource:
    """
    The agent's template as the caller may see it, like enrollment: an internal
    (non-public) template is copied only by a platform admin, others get 404.
    """

    base_url = _runtime_base_url(record, deps)
    can_see_non_public = await deps.team_dependencies.rebac.has_user_permission(
        user, PlatformPermission.CAN_MANAGE_PLATFORM, PLATFORM_ID
    )
    templates = await product_service._fetch_runtime_templates(
        base_url, include_non_public=can_see_non_public
    )
    template = next(
        (t for t in templates if t.template_agent_id == record.source_agent_id), None
    )
    if template is None:
        raise EnrollmentError(
            f"Template {record.template_id!r} was not found on runtime source "
            f"{record.source_runtime_id!r}.",
            http_status=404,
        )
    selected = record.tuning.selected_capability_ids
    if selected is None:
        # Never saved explicitly: the template defaults, as enrollment resolves them.
        available = {entry.id for entry in template.available_capabilities}
        selected = [c for c in template.default_capability_ids or [] if c in available]
    return _CopySource(
        base_url=base_url,
        capability_ids=list(selected),
        names={entry.id: entry.name for entry in template.available_capabilities},
    )


async def _destination_team_ids(
    user: KeycloakUser, deps: ProductServiceDependencies
) -> list[TeamId]:
    personal = resolve_system_team_id(user, TeamId("personal"))
    team_ids: list[TeamId] = [personal] if personal is not None else []
    refs = await deps.team_dependencies.rebac.lookup_user_resources(
        user, TeamPermission.CAN_UPDATE_AGENTS
    )
    if isinstance(refs, RebacDisabledResult):
        teams = await deps.team_dependencies.get_team_metadata_store().list_all()
        team_ids += [team.id for team in teams]
    else:
        team_ids += [TeamId(ref.id) for ref in refs]
    return list(dict.fromkeys(team_ids))


async def list_agent_copy_targets(
    *,
    user: KeycloakUser,
    record: AgentInstanceRecord,
    deps: ProductServiceDependencies,
) -> list[AgentCopyTarget]:
    """Readiness of each destination the caller edits, the source team included."""

    source = await _resolve_copy_source(user, record, deps)
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_DESTINATIONS)

    async def target(team_id: TeamId) -> AgentCopyTarget:
        async with semaphore:
            usable = await usable_capability_ids(deps.team_dependencies.rebac, team_id)
        return AgentCopyTarget(
            team_id=team_id,
            template_enabled=_template_enabled(record, usable),
            missing_capabilities=[
                AgentCopyCapability(id=cap_id, name=source.names.get(cap_id, cap_id))
                for cap_id in source.capability_ids
                if usable is not None and cap_id not in usable
            ],
        )

    return list(
        await asyncio.gather(
            *(target(team_id) for team_id in await _destination_team_ids(user, deps))
        )
    )


async def _copy_capability_config_via_pod(
    *,
    base_url: str,
    capability_id: str,
    request: CapabilityConfigCopyRequest,
    authorization: str | None,
) -> dict[str, Any] | None:
    """The pod's answer (envelope and notices), or None when the capability is left out."""

    url = f"{base_url.rstrip('/')}/agents/capabilities/{capability_id}/copy-config"
    headers = {"Authorization": authorization} if authorization else None
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url, json=request.model_dump(mode="json"), headers=headers
            )
    except httpx.RequestError as exc:
        raise EnrollmentError(
            f"Agent runtime service at {base_url} is not reachable to copy "
            f"capability '{capability_id}'.",
            http_status=503,
        ) from exc
    # 404: a pod without the operation or the capability; 422: rejected for
    # the destination. Both leave the capability out of the copy.
    if response.status_code in (404, 422):
        logger.info(
            "[control-plane][agent-copy] capability %s left out: %s %s",
            capability_id,
            response.status_code,
            response.text[:300],
        )
        return None
    if response.status_code >= 400:
        raise EnrollmentError(
            f"Agent runtime service at {base_url} returned "
            f"{response.status_code} while copying capability '{capability_id}'.",
            http_status=502,
        )
    envelope = response.json()
    if not isinstance(envelope, dict) or not {"schema_version", "config"} <= set(
        envelope
    ):
        raise EnrollmentError(
            f"Agent runtime service at {base_url} returned a malformed envelope "
            f"for capability '{capability_id}'.",
            http_status=502,
        )
    return envelope


async def _copy_name(
    record: AgentInstanceRecord,
    target_team_id: TeamId,
    deps: ProductServiceDependencies,
) -> str:
    """The source name when free in the destination, else the first free `_imported-N`."""

    existing = {
        r.display_name
        for r in await deps.get_agent_instance_store().list_by_team(target_team_id)
    }
    if record.display_name not in existing:
        return record.display_name
    base = record.display_name[:_IMPORTED_NAME_BASE_MAX]
    n = 1
    while f"{base}_imported-{n}" in existing:
        n += 1
    return f"{base}_imported-{n}"


async def copy_agent_instance_to_team(
    *,
    user: KeycloakUser,
    record: AgentInstanceRecord,
    source: _CopySource,
    target_team_id: TeamId,
    display_name: str | None,
    deps: ProductServiceDependencies,
    authorization: str | None,
) -> AgentCopyResult:
    """Create the copy of `record` in one destination the caller already edits."""

    rebac = deps.team_dependencies.rebac
    usable = await usable_capability_ids(rebac, target_team_id)
    if not _template_enabled(record, usable):
        raise EnrollmentError(
            "The agent template is not enabled for this team.", http_status=403
        )
    new_instance_id = str(uuid4())

    async def prepare(cap_id: str) -> tuple[str, dict[str, Any] | None]:
        if usable is not None and cap_id not in usable:
            return cap_id, None
        envelope = record.tuning.capability_config.get(cap_id) or {}
        request = CapabilityConfigCopyRequest.model_validate(
            {
                "config": {
                    # A slice saved before envelopes existed: the capability
                    # reads it with its own defaults.
                    "schema_version": envelope.get("schema_version") or "0",
                    "config": envelope.get("config") or {},
                },
                "source_team_id": str(record.team_id),
                "source_agent_instance_id": record.agent_instance_id,
                "target_team_id": str(target_team_id),
                "target_agent_instance_id": new_instance_id,
            }
        )
        return cap_id, await _copy_capability_config_via_pod(
            base_url=source.base_url,
            capability_id=cap_id,
            request=request,
            authorization=authorization,
        )

    prepared = await asyncio.gather(*(prepare(c) for c in source.capability_ids))
    # Persist only the envelope; notices are reported, never stored.
    kept = {
        cap_id: {"schema_version": env["schema_version"], "config": env["config"]}
        for cap_id, env in prepared
        if env is not None
    }
    dropped = [cap_id for cap_id, env in prepared if env is None]
    notices = [
        (cap_id, str(message))
        for cap_id, env in prepared
        if env is not None
        for message in env.get("notices") or []
    ]

    def capability(cap_id: str) -> AgentCopyCapability:
        return AgentCopyCapability(id=cap_id, name=source.names.get(cap_id, cap_id))

    tuning = record.tuning.model_copy(
        update={
            "selected_capability_ids": list(kept),
            "capability_config": kept,
        }
    )
    copy = AgentInstanceRecord(
        agent_instance_id=new_instance_id,
        team_id=target_team_id,
        template_id=record.template_id,
        source_runtime_id=record.source_runtime_id,
        source_agent_id=record.source_agent_id,
        display_name=display_name or await _copy_name(record, target_team_id, deps),
        description=record.description,
        enabled=True,
        created_by=user.uid,
        tuning=tuning,
    )
    created = await deps.get_agent_instance_store().create(copy)
    emit_agent_created_kpi(created, user=user, deps=deps)
    emit_audit_log(
        "agent.copied",
        source_agent_instance_id=record.agent_instance_id,
        source_team_id=str(record.team_id),
        target_team_id=str(target_team_id),
        agent_instance_id=created.agent_instance_id,
        user_id=user.uid,
        dropped_capabilities=",".join(dropped) or None,
    )
    return AgentCopyResult(
        team_id=str(target_team_id),
        agent=_record_to_summary(created),
        dropped_capabilities=[capability(cap_id) for cap_id in dropped],
        notices=[
            AgentCopyNotice(capability=capability(cap_id), message=message)
            for cap_id, message in notices
        ],
    )


async def copy_agent_instance(
    *,
    user: KeycloakUser,
    record: AgentInstanceRecord,
    target_team_ids: list[str],
    display_name: str | None,
    deps: ProductServiceDependencies,
    authorization: str | None,
    require_editor: TeamAccess,
) -> list[AgentCopyResult]:
    """Copy into every destination; a failed destination never stops the others."""

    source = await _resolve_copy_source(user, record, deps)
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_DESTINATIONS)

    async def copy_into(raw_team_id: str) -> AgentCopyResult:
        try:
            target_team_id = await require_editor(TeamId(raw_team_id))
        except HTTPException as exc:
            return AgentCopyResult(team_id=raw_team_id, error=str(exc.detail))
        try:
            async with semaphore:
                return await copy_agent_instance_to_team(
                    user=user,
                    record=record,
                    source=source,
                    target_team_id=target_team_id,
                    display_name=display_name,
                    deps=deps,
                    authorization=authorization,
                )
        except EnrollmentError as exc:
            return AgentCopyResult(team_id=str(target_team_id), error=str(exc))
        except Exception:
            # One destination's unexpected failure must not hide the others' results.
            logger.exception(
                "[control-plane][agent-copy] copy of %s into %s failed",
                record.agent_instance_id,
                target_team_id,
            )
            return AgentCopyResult(
                team_id=str(target_team_id),
                error="Unexpected error while copying the agent into this team.",
            )

    unique_team_ids = list(dict.fromkeys(target_team_ids))
    return list(await asyncio.gather(*(copy_into(t) for t in unique_team_ids)))
