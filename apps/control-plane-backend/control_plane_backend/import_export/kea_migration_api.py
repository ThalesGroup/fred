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

"""KEA CUTOVER 2026 — a single, temporary, standalone endpoint: `POST
/kea-migration/dry-run`. Preview identity/team-membership reconciliation for a
kea snapshot (zip + optional realm.json) with ZERO writes — no Keycloak, no
OpenFGA, no Postgres — so it is free to call repeatedly while iterating on an
assumption. The real apply is the EXISTING `POST /import-export/import`
(unchanged, `importer.py::run_import`), which now folds in every fix this
module adds — this file only ever *previews*, never *applies*.

⚠️ DELETE THIS FILE, its route registration in `main.py`, `kea_reconciliation.py`,
and the frontend's `KeaMigrationPage/` a few weeks after the S3NS cutover
completes — see `kea_reconciliation.py`'s own docstring for the full removal
list. Nothing outside this file and `KeaMigrationPage/` depends on the shape
of `KeaDryRunResponse`; deleting it is a self-contained revert.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fred_core import (
    ORGANIZATION_ID,
    KeycloakUser,
    OrganizationPermission,
    RebacEngine,
    get_current_user,
)
from pydantic import BaseModel

from control_plane_backend.app.dependencies import get_application_container
from control_plane_backend.import_export.agent_map import (
    AgentMapOutcome,
    classify_agent,
)
from control_plane_backend.import_export.api import MAX_UPLOAD_BYTES
from control_plane_backend.import_export.bundle import KBundle, open_bundle
from control_plane_backend.import_export.kea_reconciliation import (
    KeaReconciliationReport,
    KeaUserResolver,
    build_kea_reconciliation_plan,
)
from control_plane_backend.users.dependencies import (
    UserServiceDependencies,
    get_user_service_dependencies,
)

logger = logging.getLogger(__name__)


class KeaUserResolutionView(BaseModel):
    kea_sub: str
    kea_username: str
    outcome: str
    swift_sub: str | None


class KeaDryRunResponse(BaseModel):
    """Everything a human needs to decide "is this ready to apply", one call."""

    source_platform: str
    agents_mapped: int
    agents_ignored: int
    agents_gap: int
    agents_gap_templates: list[str]
    teams_total: int
    teams_orphan_dropped: list[str]
    teams_admin_less: list[str]
    users_matched: list[KeaUserResolutionView]
    users_relinked: list[KeaUserResolutionView]
    users_pending: list[KeaUserResolutionView]
    team_member_grants_ready: int
    team_member_grants_pending: int
    platform_role_grants_ready: int
    summary_lines: list[str]


def _get_rebac_engine(request: Request) -> RebacEngine:
    return get_application_container(request).get_rebac_engine()


def build_kea_migration_router(prefix: str = "") -> APIRouter:
    router = APIRouter(prefix=prefix, tags=["kea-migration"])

    @router.post(
        "/kea-migration/dry-run",
        response_model=KeaDryRunResponse,
        summary="[KEA CUTOVER 2026 — temporary] Preview a kea snapshot import with zero writes",
        description=(
            "Same inputs as `POST /import-export/import` (zip + optional realm_file), "
            "but performs NO write of any kind — no Keycloak, no OpenFGA, no Postgres. "
            "Safe and cheap to call repeatedly while validating an assumption (identity "
            "linking, team membership, admin coverage) before committing to a real "
            "import. Platform admin only. Temporary — removed after the S3NS cutover."
        ),
    )
    async def kea_migration_dry_run(
        file: UploadFile,
        user: Annotated[KeycloakUser, Depends(get_current_user)],
        rebac: Annotated[RebacEngine, Depends(_get_rebac_engine)],
        user_deps: Annotated[
            UserServiceDependencies, Depends(get_user_service_dependencies)
        ],
        realm_file: UploadFile | None = None,
    ) -> KeaDryRunResponse:
        await rebac.check_user_permission_or_raise(
            user, OrganizationPermission.CAN_MANAGE_PLATFORM, ORGANIZATION_ID
        )

        if not (file.filename or "").endswith(".zip"):
            raise HTTPException(
                status_code=400, detail="A .zip snapshot file is required"
            )
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Snapshot too large")

        external_realm_data: bytes | None = None
        if realm_file is not None:
            if not (realm_file.filename or "").endswith(".json"):
                raise HTTPException(
                    status_code=400, detail="realm_file must be a .json export"
                )
            external_realm_data = await realm_file.read(MAX_UPLOAD_BYTES + 1)
            if len(external_realm_data) > MAX_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="realm_file too large")

        bundle = open_bundle(data, external_realm_data=external_realm_data)
        try:
            return await _build_dry_run_response(bundle, user_deps)
        finally:
            try:
                bundle.close()
            except Exception:
                logger.warning(
                    "[kea-migration] dry-run: bundle.close() failed after the "
                    "preview itself finished — ignored, does not affect the "
                    "reported outcome",
                    exc_info=True,
                )

    return router


async def _build_dry_run_response(
    bundle: KBundle,
    user_deps: UserServiceDependencies,
) -> KeaDryRunResponse:
    is_swift_native = bundle.manifest.source_platform == "swift"

    if is_swift_native:
        return KeaDryRunResponse(
            source_platform="swift",
            agents_mapped=0,
            agents_ignored=0,
            agents_gap=0,
            agents_gap_templates=[],
            teams_total=0,
            teams_orphan_dropped=[],
            teams_admin_less=[],
            users_matched=[],
            users_relinked=[],
            users_pending=[],
            team_member_grants_ready=0,
            team_member_grants_pending=0,
            platform_role_grants_ready=0,
            summary_lines=["swift-native snapshot — kea reconciliation does not apply"],
        )

    resolver = await KeaUserResolver.create(user_deps)
    kea_report = KeaReconciliationReport()

    # Agents — classification only, no team/creator resolution needed for counts.
    gap_templates: list[str] = []
    mapped = ignored = gap = 0
    for row in bundle.iter_table("agent"):
        payload = row.get("payload_json") or {}
        if payload.get("type") == "leader":
            continue
        result = classify_agent(payload)
        if result.outcome == AgentMapOutcome.MAPPED:
            mapped += 1
        elif result.outcome == AgentMapOutcome.IGNORED:
            ignored += 1
        else:
            gap += 1
            gap_templates.append(result.kea_template or row.get("id", "<unknown>"))

    # Team merge, OpenFGA tuple restore, and platform-role resolution — the
    # exact same plan `importer.py::_run_import_body` executes for a real
    # import, computed here with zero writes.
    plan = await build_kea_reconciliation_plan(bundle, resolver, kea_report)

    def _view(items: list) -> list[KeaUserResolutionView]:  # type: ignore[type-arg]
        return [
            KeaUserResolutionView(
                kea_sub=r.kea_sub,
                kea_username=r.kea_username,
                outcome=r.outcome.value,
                swift_sub=r.swift_sub,
            )
            for r in items
        ]

    return KeaDryRunResponse(
        source_platform="kea",
        agents_mapped=mapped,
        agents_ignored=ignored,
        agents_gap=gap,
        agents_gap_templates=sorted(set(gap_templates)),
        teams_total=len(plan.team_metadata),
        teams_orphan_dropped=sorted(kea_report.orphan_teams_dropped),
        teams_admin_less=sorted(kea_report.admin_less_teams),
        users_matched=_view(kea_report.matched),
        users_relinked=_view(kea_report.relinked),
        users_pending=_view(kea_report.pending),
        team_member_grants_ready=kea_report.team_member_grants,
        team_member_grants_pending=kea_report.team_member_pending,
        platform_role_grants_ready=len(plan.realm_platform_grants),
        summary_lines=kea_report.summary_lines(),
    )
