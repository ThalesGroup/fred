# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Fresh Control Plane decisions for independent pod administration operations."""

from fastapi import HTTPException
from fred_core.security.control_plane import allowed_response, authorization_request

from fred_runtime.runtime_context import get_runtime_context


async def is_allowed(
    authorization: str | None, permission: str, *, space_id: str | None = None
) -> bool:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "credential_required")
    runtime = get_runtime_context().config
    if not runtime.control_plane_url or runtime.control_plane_http_client is None:
        raise HTTPException(503, "authorization_unavailable")
    body = {"permission": permission}
    if space_id is not None:
        body["space_id"] = space_id
    result = await authorization_request(
        runtime.control_plane_http_client,
        f"{runtime.control_plane_url.rstrip('/')}/authorize/{'space' if space_id is not None else 'platform'}",
        body,
        headers={"Authorization": authorization},
        auth=None,
    )
    return allowed_response(result)


async def require_permission(
    authorization: str | None, permission: str, *, space_id: str | None = None
) -> None:
    if not await is_allowed(authorization, permission, space_id=space_id):
        raise HTTPException(403, "access_denied")
