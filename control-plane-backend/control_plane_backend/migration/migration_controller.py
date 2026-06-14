# Copyright Thales 2025
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

"""Platform-admin-only endpoints for the one-shot kea migration."""

from __future__ import annotations

import base64
import io
import logging

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse
from fred_core import KeycloakUser, get_current_user, require_admin

from control_plane_backend.migration.export_service import (
    build_snapshot,
    export_kea_snapshot,
)
from control_plane_backend.migration.import_service import import_kea_snapshot
from control_plane_backend.migration.snapshot import (
    ImportReport,
    SnapshotRequest,
    SnapshotResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Migration"])


@router.post(
    "/admin/migration/snapshot",
    response_model=SnapshotResponse,
    response_model_exclude_none=True,
    summary="Export a full kea snapshot bundle (platform admin only)",
)
async def create_snapshot(
    request: SnapshotRequest | None = None,
    user: KeycloakUser = Depends(get_current_user),
) -> SnapshotResponse:
    """Snapshot durable platform state into a downloadable bundle.

    Restricted to platform admins. Captures Postgres user data, OpenFGA tuples,
    the Keycloak realm, and team banner content into a single zip stored in
    object storage, returning a presigned download URL.
    """
    require_admin(user)
    logger.info("[SNAPSHOT] export requested by %s", user.uid)
    return await export_kea_snapshot(label=request.label if request else None)


@router.post(
    "/admin/migration/snapshot/download",
    summary="Build and stream a kea snapshot bundle directly (platform admin only)",
)
async def download_snapshot(
    request: SnapshotRequest | None = None,
    user: KeycloakUser = Depends(get_current_user),
) -> StreamingResponse:
    """Stream the snapshot zip straight through the API (no object storage).

    Restricted to platform admins. Intended for cross-infrastructure migrations
    where the caller can reach the kea API but not its object storage. The
    manifest travels in a base64 ``X-Migration-Manifest`` header.
    """
    require_admin(user)
    logger.info("[SNAPSHOT] direct download requested by %s", user.uid)
    filename, data, manifest = await build_snapshot(
        label=request.label if request else None
    )
    manifest_b64 = base64.b64encode(manifest.model_dump_json().encode()).decode()
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Migration-Manifest": manifest_b64,
        "Access-Control-Expose-Headers": "Content-Disposition, X-Migration-Manifest",
    }
    return StreamingResponse(
        io.BytesIO(data), media_type="application/zip", headers=headers
    )


@router.post(
    "/admin/migration/import",
    response_model=ImportReport,
    summary="Restore a kea snapshot bundle into this kea (platform admin only)",
)
async def import_snapshot(
    file: UploadFile = File(...),
    user: KeycloakUser = Depends(get_current_user),
) -> ImportReport:
    """Restore an uploaded kea snapshot bundle into the current kea instance.

    Restricted to platform admins. Upserts Postgres rows and replays OpenFGA
    tuples (diff-based). Keycloak realm is not imported (shared realm). Writes to
    the database and OpenFGA store — intended for a fresh/empty target.
    """
    require_admin(user)
    logger.info("[IMPORT] import requested by %s (file=%s)", user.uid, file.filename)
    return await import_kea_snapshot(await file.read())
