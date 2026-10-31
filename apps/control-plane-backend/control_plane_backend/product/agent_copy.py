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
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx
from fastapi import HTTPException
from fred_core import (
    ORGANIZATION_ID,
    KeycloakUser,
    OrganizationPermission,
    TeamPermission,
)
from fred_core.common import TeamId
from fred_core.logs.audit_log import emit_audit_log
from fred_core.security.rebac.rebac_engine import RebacDisabledResult
from fred_sdk.contracts.capability import CapabilityConfigCopyRequest

from control_plane_backend.agent_instances.names import (
    CopyLocale,
    free_imported_name,
    normalize_agent_name,
)
from control_plane_backend.agent_instances.store import (
    AgentInstanceRecord,
    AgentNameAlreadyExistsError,
)
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
    agent_name_conflict,
    capability_gate_exempt,
    emit_agent_created_kpi,
    template_capability_id,
)
from control_plane_backend.teams.system import resolve_system_team_id

logger = logging.getLogger(__name__)

# Destinations are prepared concurrently, each one calling the pod once per
# capability; keep the fan-out small.
_MAX_CONCURRENT_DESTINATIONS = 4

TeamAccess = Callable[[TeamId], Awaitable[TeamId]]


def runtime_base_url(
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
class CopySource:
    """What every destination of one copy request shares."""

    base_url: str
    capability_ids: list[str]
    names: dict[str, str]


async def effective_capability_ids(
    record: AgentInstanceRecord, template: Any, deps: ProductServiceDependencies
) -> list[str]:
    """
    The capabilities the agent actually runs: its stored selection, else (never
    saved, or a template without free selection) the defaults, as a save resolves them.
    """
    selected = record.tuning.selected_capability_ids
    if selected is not None and template.supports_capabilities:
        return list(selected)
    return await product_service.template_default_capability_ids(
        template.available_capabilities,
        template.default_capability_ids or [],
        record.team_id,
        deps,
    )


async def _resolve_copy_source(
    user: KeycloakUser, record: AgentInstanceRecord, deps: ProductServiceDependencies
) -> CopySource:
    """
    The agent's template as the caller may see it, like enrollment: an internal
    (non-public) template is copied only by a platform admin, others get 404.
    """

    base_url = runtime_base_url(record, deps)
    can_see_non_public = await deps.team_dependencies.rebac.has_user_permission(
        user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID
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
    return CopySource(
        base_url=base_url,
        capability_ids=await effective_capability_ids(record, template, deps),
        names={entry.id: entry.name for entry in template.available_capabilities},
    )


async def destination_team_ids(
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
    return await copy_targets(
        record=record,
        source=source,
        team_ids=await destination_team_ids(user, deps),
        deps=deps,
    )


async def copy_targets(
    *,
    record: AgentInstanceRecord,
    source: CopySource,
    team_ids: list[TeamId],
    deps: ProductServiceDependencies,
) -> list[AgentCopyTarget]:
    """Per destination: template enabled, and the capabilities it cannot use."""

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

    return list(await asyncio.gather(*(target(team_id) for team_id in team_ids)))


async def _copy_capability_config_via_pod(
    *,
    base_url: str,
    capability_id: str,
    request: CapabilityConfigCopyRequest,
    authorization: str | None,
    routing_params: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """The pod's answer (envelope and notices), or None when the capability is left out.
    `routing_params` carry the destination team's routing, as on a save."""

    url = f"{base_url.rstrip('/')}/agents/capabilities/{capability_id}/copy-config"
    headers = {"Authorization": authorization} if authorization else None
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
                json=request.model_dump(mode="json"),
                headers=headers,
                params=routing_params or None,
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
    locale: CopyLocale | None,
) -> str:
    """The source name when free in the destination, else `<name> (copy N)` in `locale`."""

    taken = {
        normalize_agent_name(r.display_name)
        for r in await deps.get_agent_instance_store().list_by_team(target_team_id)
    }
    return free_imported_name(record.display_name, taken, locale)


async def _ensure_duplicate_name_free(
    target_team_id: TeamId, display_name: str, deps: ProductServiceDependencies
) -> None:
    taken = {
        normalize_agent_name(r.display_name)
        for r in await deps.get_agent_instance_store().list_by_team(target_team_id)
    }
    if normalize_agent_name(display_name) in taken:
        raise agent_name_conflict(target_team_id, display_name)


async def copy_agent_instance_to_team(
    *,
    user: KeycloakUser,
    record: AgentInstanceRecord,
    source: CopySource,
    target_team_id: TeamId,
    display_name: str | None,
    deps: ProductServiceDependencies,
    authorization: str | None,
    asset_files: Mapping[str, dict[str, str]] | None = None,
    locale: CopyLocale | None = None,
) -> AgentCopyResult:
    """Create the copy of `record` in one destination the caller already edits.

    `asset_files` (capability id → files) copies from a stored snapshot: the
    pod takes the files from there and never reads the source team.
    """

    rebac = deps.team_dependencies.rebac
    usable = await usable_capability_ids(rebac, target_team_id)
    if not _template_enabled(record, usable):
        raise EnrollmentError(
            "The agent template is not enabled for this team.", http_status=403
        )
    # A duplicate keeps the name the user chose, so it is refused before the
    # pod prepares anything; a copy picks a free name instead.
    if display_name is not None:
        await _ensure_duplicate_name_free(target_team_id, display_name, deps)
    new_instance_id = str(uuid4())
    routing_params = (
        await product_service._capability_save_routing_params(
            deps,
            target_team_id,
            record.source_agent_id,
            record.tuning.recommended_chat_profile_id,
        )
        if source.capability_ids
        else None
    )

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
                "asset_files": (
                    asset_files.get(cap_id, {}) if asset_files is not None else None
                ),
            }
        )
        return cap_id, await _copy_capability_config_via_pod(
            base_url=source.base_url,
            capability_id=cap_id,
            request=request,
            authorization=authorization,
            routing_params=routing_params,
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
        display_name=display_name
        or await _copy_name(record, target_team_id, deps, locale),
        description=record.description,
        enabled=True,
        created_by=user.uid,
        tuning=tuning,
    )
    store = deps.get_agent_instance_store()
    try:
        created = await store.create(copy)
    except AgentNameAlreadyExistsError as exc:
        if display_name is not None:
            raise agent_name_conflict(target_team_id, display_name) from exc
        # A concurrent copy took the name: pick the next free one, once.
        copy.display_name = await _copy_name(record, target_team_id, deps, locale)
        try:
            created = await store.create(copy)
        except AgentNameAlreadyExistsError as again:
            raise agent_name_conflict(target_team_id, copy.display_name) from again
    # A copied capability may start preparing again in the destination.
    created = await product_service.settle_capability_save(
        deps, created, authorization=authorization
    )
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
    source: CopySource | None = None,
    asset_files: Mapping[str, dict[str, str]] | None = None,
    refused_team_id: TeamId | None = None,
    on_copied: Callable[[AgentCopyResult], Awaitable[None]] | None = None,
    locale: CopyLocale | None = None,
) -> list[AgentCopyResult]:
    """Copy into every destination; a failed destination never stops the others.

    A marketplace import passes the snapshot as `source` and `asset_files`,
    refuses the publishing team, and records each success with `on_copied`.
    """

    if source is None:
        source = await _resolve_copy_source(user, record, deps)
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_DESTINATIONS)

    async def copy_into(raw_team_id: str) -> AgentCopyResult:
        try:
            target_team_id = await require_editor(TeamId(raw_team_id))
        except HTTPException as exc:
            return AgentCopyResult(team_id=raw_team_id, error=str(exc.detail))
        if target_team_id == refused_team_id:
            return AgentCopyResult(
                team_id=str(target_team_id),
                error="An agent cannot be imported into the team that published it.",
                error_code="marketplace_publishing_team",
            )
        try:
            async with semaphore:
                result = await copy_agent_instance_to_team(
                    user=user,
                    record=record,
                    source=source,
                    target_team_id=target_team_id,
                    display_name=display_name,
                    deps=deps,
                    authorization=authorization,
                    asset_files=asset_files,
                    locale=locale,
                )
        except EnrollmentError as exc:
            return AgentCopyResult(
                team_id=str(target_team_id), error=str(exc), error_code=exc.code
            )
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
        if on_copied is not None:
            try:
                await on_copied(result)
            except Exception:
                # The copy exists; losing its bookkeeping must not report a failure.
                logger.exception(
                    "[control-plane][agent-copy] recording the copy into %s failed",
                    target_team_id,
                )
        return result

    unique_team_ids = list(dict.fromkeys(target_team_ids))
    return list(await asyncio.gather(*(copy_into(t) for t in unique_team_ids)))
