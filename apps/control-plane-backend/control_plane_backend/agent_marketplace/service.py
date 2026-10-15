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

"""Publish a team agent as a snapshot, take it down, like and import it.

Publication exports every capability through its pod (`export-config`) with
the publishing editor's token; import reuses the agent copy on the stored snapshot, so
it never reads the publishing team.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

import httpx
from fred_core import (
    ORGANIZATION_ID,
    KeycloakUser,
    OrganizationPermission,
    TeamPermission,
)
from fred_core.common import TeamId, is_personal_team_id
from fred_core.logs.audit_log import emit_audit_log
from fred_core.teams.metadata_store import TeamVisibility
from fred_sdk.contracts.capability import (
    CapabilityConfigExportRequest,
    CapabilityConfigExportResult,
)
from pydantic import ValidationError

from control_plane_backend.agent_instances.names import CopyLocale
from control_plane_backend.agent_instances.store import AgentInstanceRecord
from control_plane_backend.agent_marketplace.schemas import (
    MarketplaceAgentCapability,
    MarketplaceAgentDetail,
    MarketplaceAgentFile,
    MarketplaceAgentSummary,
    PublishAgentRequest,
    UnpublishAgentRequest,
)
from control_plane_backend.agent_marketplace.store import (
    AgentMarketplaceStore,
    EntryCounters,
    EntryState,
    ListedEntry,
    MarketplaceAgentInactive,
    MarketplaceEntry,
    MarketplaceEntryNotFound,
    MarketplacePublishingClosed,
    MarketplaceQuotaReached,
    MarketplaceVersionConflict,
    RemovalReason,
    Snapshot,
    SnapshotFile,
    emit_unpublished,
)
from control_plane_backend.config.models import ManagedAgentTuning
from control_plane_backend.marketplace_settings.effective import (
    effective_marketplace_settings,
    load_marketplace_default,
)
from control_plane_backend.product import service as product_service
from control_plane_backend.product.agent_copy import (
    CopySource,
    TeamAccess,
    copy_agent_instance,
    copy_targets,
    destination_team_ids,
    effective_capability_ids,
    runtime_base_url,
)
from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.product.schemas import (
    AgentCopyResult,
    AgentCopyTarget,
    AgentMarketplaceState,
    ManagedAgentInstanceSummary,
)
from control_plane_backend.product.service import EnrollmentError
from control_plane_backend.teams.system import resolve_system_team_id

logger = logging.getLogger(__name__)

# Files travel in base64 JSON; generous for a pod reading its own storage.
_EXPORT_TIMEOUT_SECONDS = 60.0


class MarketplaceError(Exception):
    """A refused marketplace operation, with its HTTP status and a stable code."""

    def __init__(
        self,
        message: str,
        *,
        http_status: int,
        code: str,
        capability_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.code = code
        self.capability_id = capability_id


def _store(deps: ProductServiceDependencies) -> AgentMarketplaceStore:
    return deps.get_agent_marketplace_store()


def _version_conflict() -> MarketplaceError:
    return MarketplaceError(
        "The agent's marketplace entry changed meanwhile; refresh and try again.",
        http_status=409,
        code="marketplace_version_conflict",
    )


def _quota_reached(quota: int) -> MarketplaceError:
    return MarketplaceError(
        f"The team already has {quota} published agents, its quota.",
        http_status=409,
        code="marketplace_quota_reached",
    )


def _is_personal(user: KeycloakUser, team_id: TeamId) -> bool:
    return resolve_system_team_id(user, team_id) is not None or is_personal_team_id(
        team_id
    )


def _state_view(
    entry: MarketplaceEntry,
    counters: EntryCounters,
    *,
    agent_updated_at: Any,
    full: bool,
) -> AgentMarketplaceState | None:
    """The card's view of an entry; members who are not editors only see Published."""
    published = entry.state == EntryState.PUBLISHED
    if not full and not published:
        return None
    return AgentMarketplaceState(
        state=entry.state.value,
        version=entry.version,
        published_at=entry.published_at,
        modified=(
            full and published and agent_updated_at != entry.snapshot_source_updated_at
        ),
        removed_reason=entry.removed_reason if full else None,
        removed_message=entry.removed_message if full else None,
        removed_at=entry.removed_at if full else None,
        like_count=counters.like_count,
        import_count=counters.import_count,
    )


async def attach_marketplace_states(
    *,
    user: KeycloakUser,
    team_id: TeamId,
    summaries: Sequence[ManagedAgentInstanceSummary],
    deps: ProductServiceDependencies,
) -> None:
    """Fill `marketplace` on the team listing: one entries read, two grouped
    counter queries and one permission check, only when something is published."""
    if _is_personal(user, team_id):
        return
    store = _store(deps)
    entries = await store.list_for_team(team_id)
    if not entries:
        return
    # Editors and the team admin see Modified and Removed; others only Published.
    counters, full = await asyncio.gather(
        store.counters([entry.entry_id for entry in entries]),
        deps.team_dependencies.rebac.has_user_permission(
            user, TeamPermission.CAN_UNPUBLISH_MARKETPLACE_AGENTS, team_id
        ),
    )
    by_agent = {entry.agent_instance_id: entry for entry in entries}
    for summary in summaries:
        entry = by_agent.get(summary.agent_instance_id)
        if entry is None:
            continue
        summary.marketplace = _state_view(
            entry,
            counters.get(entry.entry_id, EntryCounters()),
            agent_updated_at=summary.updated_at,
            full=full,
        )


async def _public_template(
    record: AgentInstanceRecord, deps: ProductServiceDependencies
) -> Any:
    """The agent's template when the pod lists it publicly, else None."""
    base_url = runtime_base_url(record, deps)
    templates = await product_service._fetch_runtime_templates(
        base_url, include_non_public=False
    )
    return next(
        (t for t in templates if t.template_agent_id == record.source_agent_id), None
    )


async def _export_capability(
    *,
    deps: ProductServiceDependencies,
    base_url: str,
    capability_id: str,
    request: CapabilityConfigExportRequest,
    authorization: str | None,
) -> CapabilityConfigExportResult:
    url = f"{base_url.rstrip('/')}/agents/capabilities/{capability_id}/export-config"
    headers = {"Authorization": authorization} if authorization else None
    try:
        response = await deps.get_runtime_http_client().post(
            url,
            json=request.model_dump(mode="json"),
            headers=headers,
            timeout=_EXPORT_TIMEOUT_SECONDS,
        )
    except httpx.RequestError as exc:
        raise MarketplaceError(
            f"The agent runtime is not reachable to export capability "
            f"'{capability_id}'.",
            http_status=503,
            code="marketplace_runtime_unavailable",
            capability_id=capability_id,
        ) from exc
    if response.status_code == 404:
        raise MarketplaceError(
            f"Capability '{capability_id}' is not installed on the agent runtime "
            "or cannot be exported.",
            http_status=422,
            code="marketplace_capability_not_exportable",
            capability_id=capability_id,
        )
    if response.status_code == 422:
        raise MarketplaceError(
            f"Capability '{capability_id}' could not prepare its configuration: "
            f"{response.text[:300]}",
            http_status=422,
            code="marketplace_capability_not_exportable",
            capability_id=capability_id,
        )
    if response.status_code >= 400:
        raise MarketplaceError(
            f"The agent runtime returned {response.status_code} while exporting "
            f"capability '{capability_id}'.",
            http_status=503,
            code="marketplace_runtime_unavailable",
            capability_id=capability_id,
        )
    try:
        return CapabilityConfigExportResult.model_validate(response.json())
    except (ValidationError, ValueError) as exc:
        raise MarketplaceError(
            f"The agent runtime returned a malformed export for capability "
            f"'{capability_id}'.",
            http_status=503,
            code="marketplace_runtime_unavailable",
            capability_id=capability_id,
        ) from exc


def _decode_files(
    capability_id: str, exported: CapabilityConfigExportResult
) -> list[SnapshotFile]:
    files: list[SnapshotFile] = []
    for asset_key, encoded in exported.files.items():
        try:
            content = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise MarketplaceError(
                f"Capability '{capability_id}' returned an unreadable file.",
                http_status=422,
                code="marketplace_capability_not_exportable",
                capability_id=capability_id,
            ) from exc
        files.append(
            SnapshotFile(
                capability_id=capability_id,
                asset_key=asset_key,
                filename=asset_key.rsplit("/", 1)[-1][:255],
                content=content,
            )
        )
    return files


def _values_without_secrets(
    tuning: ManagedAgentTuning, template: Any
) -> dict[str, Any]:
    """Drop every value a field declares `secret`, by the instance's stored
    fields or the template's: a retyped declaration must not expose it."""
    declared = [*tuning.fields, *template.default_tuning.fields]
    secret = {field.key for field in declared if str(field.type) == "secret"}
    return {key: value for key, value in tuning.values.items() if key not in secret}


async def _build_snapshot(
    *,
    record: AgentInstanceRecord,
    template: Any,
    deps: ProductServiceDependencies,
    authorization: str | None,
) -> Snapshot:
    """Export every selected capability; any failure fails the whole publication."""
    selected = await effective_capability_ids(record, template, deps)
    entries = {entry.id: entry for entry in template.available_capabilities}
    base_url = runtime_base_url(record, deps)

    async def export(capability_id: str) -> CapabilityConfigExportResult:
        envelope = record.tuning.capability_config.get(capability_id) or {}
        request = CapabilityConfigExportRequest.model_validate(
            {
                "config": {
                    "schema_version": envelope.get("schema_version") or "0",
                    "config": envelope.get("config") or {},
                },
                "team_id": str(record.team_id),
                "agent_instance_id": record.agent_instance_id,
            }
        )
        return await _export_capability(
            deps=deps,
            base_url=base_url,
            capability_id=capability_id,
            request=request,
            authorization=authorization,
        )

    exported = await asyncio.gather(*(export(c) for c in selected))
    tuning = record.tuning.model_copy(
        update={
            "values": _values_without_secrets(record.tuning, template),
            "selected_capability_ids": list(selected),
            "capability_config": {
                cap_id: {
                    "schema_version": result.schema_version,
                    "config": result.config,
                }
                for cap_id, result in zip(selected, exported)
            },
        }
    )
    return Snapshot(
        template_id=record.template_id,
        source_runtime_id=record.source_runtime_id,
        source_agent_id=record.source_agent_id,
        display_name=record.display_name,
        description=record.description,
        tuning_json=tuning.model_dump_json(),
        capabilities=[
            {
                "id": cap_id,
                "name": entries[cap_id].name if cap_id in entries else cap_id,
                "description": (
                    entries[cap_id].description if cap_id in entries else None
                ),
                "icon": entries[cap_id].icon if cap_id in entries else None,
            }
            for cap_id in selected
        ],
        # Stored records always carry it; the column is NOT NULL.
        source_updated_at=cast(datetime, record.updated_at),
        files=[
            file
            for cap_id, result in zip(selected, exported)
            for file in _decode_files(cap_id, result)
        ],
    )


def _team_private() -> MarketplaceError:
    return MarketplaceError(
        "Private teams cannot publish agents.",
        http_status=409,
        code="marketplace_team_private",
    )


def _agent_inactive() -> MarketplaceError:
    return MarketplaceError(
        "A deactivated or suspended agent cannot be published.",
        http_status=409,
        code="marketplace_agent_inactive",
    )


def _switch_off() -> MarketplaceError:
    return MarketplaceError(
        "Publishing agents is not enabled for this team.",
        http_status=409,
        code="marketplace_switch_off",
    )


async def publish_agent(
    *,
    user: KeycloakUser,
    team_id: TeamId,
    agent_instance_id: str,
    request: PublishAgentRequest,
    deps: ProductServiceDependencies,
    authorization: str | None,
) -> AgentMarketplaceState:
    """Publish or republish; a failure never touches the published snapshot."""
    if _is_personal(user, team_id):
        raise MarketplaceError(
            "Agents of a personal space cannot be published.",
            http_status=403,
            code="marketplace_personal_space",
        )
    await deps.team_dependencies.rebac.check_user_permission_or_raise(
        user, TeamPermission.CAN_PUBLISH_MARKETPLACE_AGENTS, team_id
    )
    # Read before the export: a save made meanwhile still shows as Modified.
    record = await deps.get_agent_instance_store().get_for_team(
        agent_instance_id, team_id
    )
    metadata = await deps.get_team_metadata_store().get_by_team_id(team_id)
    if record is None or metadata is None:
        raise MarketplaceError(
            f"Agent instance {agent_instance_id!r} not found for team {team_id!r}.",
            http_status=404,
            code="marketplace_agent_not_found",
        )
    # Deactivation and suspension take an entry down; publishing must not undo that.
    if not record.enabled or record.suspension_reason is not None:
        raise _agent_inactive()
    if metadata.visibility != TeamVisibility.PUBLIC:
        raise _team_private()
    default = await load_marketplace_default(
        deps.team_dependencies.get_marketplace_settings_store
    )
    settings = effective_marketplace_settings(default, metadata)
    if not settings.agents_publishing_enabled:
        raise _switch_off()
    store = _store(deps)
    # Fail fast before the pod round-trips; the locked write re-checks both.
    current = await store.get_for_agent(agent_instance_id, team_id)
    if (current.version if current else None) != request.expected_version:
        raise _version_conflict()
    if current is None or current.state != EntryState.PUBLISHED:
        published = (await store.count_published([team_id]))[team_id]
        if published >= settings.agents_publish_quota:
            raise _quota_reached(settings.agents_publish_quota)
    try:
        template = await _public_template(record, deps)
    except EnrollmentError as exc:
        raise MarketplaceError(
            str(exc), http_status=503, code="marketplace_runtime_unavailable"
        ) from exc
    if template is None:
        raise MarketplaceError(
            "This agent uses an agent type reserved to platform administrators: "
            "it cannot be published.",
            http_status=409,
            code="marketplace_template_not_public",
        )
    snapshot = await _build_snapshot(
        record=record, template=template, deps=deps, authorization=authorization
    )
    try:
        entry, is_new = await store.save_publication(
            agent_instance_id=agent_instance_id,
            team_id=team_id,
            snapshot=snapshot,
            expected_version=request.expected_version,
        )
    except MarketplaceVersionConflict as exc:
        raise _version_conflict() from exc
    except MarketplaceQuotaReached as exc:
        raise _quota_reached(exc.quota) from exc
    except MarketplacePublishingClosed as exc:
        raise (_team_private() if exc.team_private else _switch_off()) from exc
    except MarketplaceAgentInactive as exc:
        raise _agent_inactive() from exc
    emit_audit_log(
        "agent.published",
        entry_id=entry.entry_id,
        agent_instance_id=agent_instance_id,
        team_id=str(team_id),
        version=entry.version,
        republished=not is_new,
        user_id=user.uid,
    )
    counters = (await store.counters([entry.entry_id]))[entry.entry_id]
    view = _state_view(entry, counters, agent_updated_at=record.updated_at, full=True)
    assert view is not None
    return view


async def can_remove_from_marketplace(
    user: KeycloakUser, team_id: TeamId, deps: ProductServiceDependencies
) -> tuple[bool, bool]:
    """(team permission, platform admin): editors and the team admin of the
    agent's team, or a platform admin, may remove an entry."""
    rebac = deps.team_dependencies.rebac
    in_team, platform = await asyncio.gather(
        rebac.has_user_permission(
            user, TeamPermission.CAN_UNPUBLISH_MARKETPLACE_AGENTS, team_id
        ),
        rebac.has_user_permission(
            user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID
        ),
    )
    return in_team, platform


async def unpublish_agent(
    *,
    user: KeycloakUser,
    team_id: TeamId,
    agent_instance_id: str,
    request: UnpublishAgentRequest,
    deps: ProductServiceDependencies,
) -> None:
    """A removal by the team leaves no Removed state; a platform admin's does,
    with its optional reason."""
    if _is_personal(user, team_id):
        raise MarketplaceError(
            "Agents of a personal space are never published.",
            http_status=404,
            code="marketplace_entry_not_found",
        )
    in_team, platform = await can_remove_from_marketplace(user, team_id, deps)
    if not (in_team or platform) or (request.reason and not platform):
        raise MarketplaceError(
            "Not allowed to remove this agent from the marketplace.",
            http_status=403,
            code="marketplace_forbidden",
        )
    by_team = in_team and not request.reason
    try:
        removed = await _store(deps).remove(
            agent_instance_id=agent_instance_id,
            team_id=team_id,
            expected_version=request.expected_version,
            reason=(
                RemovalReason.REMOVED_BY_TEAM
                if by_team
                else RemovalReason.REMOVED_BY_PLATFORM_ADMIN
            ),
            message=None if by_team else request.reason,
        )
    except MarketplaceVersionConflict as exc:
        raise _version_conflict() from exc
    except MarketplaceEntryNotFound as exc:
        raise MarketplaceError(
            "This agent is not published.",
            http_status=404,
            code="marketplace_entry_not_found",
        ) from exc
    emit_unpublished([removed], actor_uid=user.uid)


async def dismiss_marketplace_removal(
    *,
    user: KeycloakUser,
    team_id: TeamId,
    agent_instance_id: str,
    deps: ProductServiceDependencies,
) -> None:
    """Hide the Removed state for the whole team (editors and team admin)."""
    await deps.team_dependencies.rebac.check_user_permission_or_raise(
        user, TeamPermission.CAN_UNPUBLISH_MARKETPLACE_AGENTS, team_id
    )
    try:
        await _store(deps).dismiss(agent_instance_id=agent_instance_id, team_id=team_id)
    except MarketplaceEntryNotFound as exc:
        raise MarketplaceError(
            "This agent has no marketplace removal to hide.",
            http_status=404,
            code="marketplace_entry_not_found",
        ) from exc


def _summary_fields(
    entry: MarketplaceEntry | ListedEntry,
    team_name: str | None,
    counters: EntryCounters,
    liked: bool,
    role: str,
) -> dict[str, Any]:
    return {
        "entry_id": entry.entry_id,
        "team_id": entry.team_id,
        "team_name": team_name,
        "template_id": entry.template_id,
        "display_name": entry.display_name,
        "description": entry.description,
        "role": role,
        "version": entry.version,
        "first_published_at": entry.first_published_at,
        "published_at": entry.published_at,
        "like_count": counters.like_count,
        "import_count": counters.import_count,
        "liked_by_me": liked,
    }


def _tuning(entry: MarketplaceEntry) -> ManagedAgentTuning:
    return ManagedAgentTuning.model_validate_json(entry.tuning_json)


async def list_marketplace_agents(
    *,
    user: KeycloakUser,
    q: str | None,
    team_id: TeamId | None,
    deps: ProductServiceDependencies,
) -> list[MarketplaceAgentSummary]:
    store = _store(deps)
    rows = await store.list_published(q=q, team_id=team_id)
    ids = [entry.entry_id for entry in rows]
    counters, liked = await asyncio.gather(
        store.counters(ids), store.liked_by(user.uid, ids)
    )
    return [
        MarketplaceAgentSummary(
            **_summary_fields(
                entry,
                entry.team_name,
                counters.get(entry.entry_id, EntryCounters()),
                entry.entry_id in liked,
                entry.role,
            )
        )
        for entry in rows
    ]


async def _published_entry(
    entry_id: str, deps: ProductServiceDependencies
) -> MarketplaceEntry:
    entry = await _store(deps).get_published(entry_id)
    if entry is None:
        raise MarketplaceError(
            f"Marketplace agent {entry_id!r} not found.",
            http_status=404,
            code="marketplace_entry_not_found",
        )
    return entry


async def get_marketplace_agent(
    *, user: KeycloakUser, entry_id: str, deps: ProductServiceDependencies
) -> MarketplaceAgentDetail:
    store = _store(deps)
    entry = await _published_entry(entry_id, deps)
    team_name, counters, liked, files = await asyncio.gather(
        store.team_name(entry.team_id),
        store.counters([entry_id]),
        store.liked_by(user.uid, [entry_id]),
        store.list_files(entry_id),
    )
    tuning = _tuning(entry)
    entry_counters = counters.get(entry_id, EntryCounters())
    return MarketplaceAgentDetail(
        **_summary_fields(
            entry, team_name, entry_counters, entry_id in liked, tuning.role
        ),
        agent_instance_id=entry.agent_instance_id,
        likes_since_update=entry_counters.likes_since_update,
        usage_statement=tuning.usage_statement,
        tuning_field_values=tuning.values,
        capabilities=[
            MarketplaceAgentCapability.model_validate(item)
            for item in entry.capabilities
        ],
        files=[
            MarketplaceAgentFile(
                capability_id=file.capability_id, filename=file.filename, size=file.size
            )
            for file in files
        ],
    )


async def set_marketplace_like(
    *,
    user: KeycloakUser,
    entry_id: str,
    liked: bool,
    deps: ProductServiceDependencies,
) -> MarketplaceAgentSummary:
    store = _store(deps)
    try:
        await store.set_like(entry_id, user.uid, liked=liked)
    except MarketplaceEntryNotFound as exc:
        raise MarketplaceError(
            f"Marketplace agent {entry_id!r} not found.",
            http_status=404,
            code="marketplace_entry_not_found",
        ) from exc
    entry = await _published_entry(entry_id, deps)
    team_name, counters, liked_ids = await asyncio.gather(
        store.team_name(entry.team_id),
        store.counters([entry_id]),
        store.liked_by(user.uid, [entry_id]),
    )
    return MarketplaceAgentSummary(
        **_summary_fields(
            entry,
            team_name,
            counters.get(entry_id, EntryCounters()),
            entry_id in liked_ids,
            _tuning(entry).role,
        )
    )


def _snapshot_source(
    entry: MarketplaceEntry, deps: ProductServiceDependencies
) -> tuple[AgentInstanceRecord, CopySource]:
    """The snapshot as the agent copy's source: the publishing team as source
    team and the entry id as source agent, so nothing is read from them."""
    tuning = _tuning(entry)
    record = AgentInstanceRecord(
        agent_instance_id=entry.entry_id,
        team_id=entry.team_id,
        template_id=entry.template_id,
        source_runtime_id=entry.source_runtime_id,
        source_agent_id=entry.source_agent_id,
        display_name=entry.display_name,
        description=entry.description,
        enabled=True,
        created_by=None,
        tuning=tuning,
    )
    try:
        base_url = runtime_base_url(record, deps)
    except EnrollmentError as exc:
        raise MarketplaceError(
            str(exc), http_status=503, code="marketplace_runtime_unavailable"
        ) from exc
    source = CopySource(
        base_url=base_url,
        capability_ids=list(tuning.selected_capability_ids or []),
        names={item["id"]: item["name"] for item in entry.capabilities},
    )
    return record, source


async def _require_importable_template(
    user: KeycloakUser, record: AgentInstanceRecord, deps: ProductServiceDependencies
) -> None:
    """An agent type that turned administrator-only after publication is
    imported only by a platform admin, as Copy to... resolves it."""
    if await deps.team_dependencies.rebac.has_user_permission(
        user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID
    ):
        return
    try:
        template = await _public_template(record, deps)
    except EnrollmentError as exc:
        raise MarketplaceError(
            str(exc), http_status=503, code="marketplace_runtime_unavailable"
        ) from exc
    if template is None:
        raise MarketplaceError(
            "This agent uses an agent type reserved to platform administrators: "
            "it cannot be imported.",
            http_status=409,
            code="marketplace_template_not_public",
        )


async def list_marketplace_import_targets(
    *, user: KeycloakUser, entry_id: str, deps: ProductServiceDependencies
) -> list[AgentCopyTarget]:
    entry = await _published_entry(entry_id, deps)
    record, source = _snapshot_source(entry, deps)
    await _require_importable_template(user, record, deps)
    team_ids = [
        team_id
        for team_id in await destination_team_ids(user, deps)
        if team_id != entry.team_id
    ]
    return await copy_targets(
        record=record, source=source, team_ids=team_ids, deps=deps
    )


async def import_marketplace_agent(
    *,
    user: KeycloakUser,
    entry_id: str,
    target_team_ids: list[str],
    deps: ProductServiceDependencies,
    authorization: str | None,
    require_editor: TeamAccess,
    locale: CopyLocale | None = None,
) -> list[AgentCopyResult]:
    """Copy the snapshot into each destination; one import row per success."""
    store = _store(deps)
    entry = await _published_entry(entry_id, deps)
    record, source = _snapshot_source(entry, deps)
    await _require_importable_template(user, record, deps)
    asset_files = await store.asset_files(entry_id)

    async def record_import(result: AgentCopyResult) -> None:
        assert result.agent is not None
        await store.record_import(
            entry_id=entry_id,
            target_team_id=TeamId(result.team_id),
            user_id=user.uid,
            agent_instance_id=result.agent.agent_instance_id,
            version=entry.version,
        )

    return await copy_agent_instance(
        user=user,
        record=record,
        target_team_ids=target_team_ids,
        display_name=None,
        deps=deps,
        authorization=authorization,
        require_editor=require_editor,
        source=source,
        asset_files=asset_files,
        refused_team_id=entry.team_id,
        on_copied=record_import,
        locale=locale,
    )
