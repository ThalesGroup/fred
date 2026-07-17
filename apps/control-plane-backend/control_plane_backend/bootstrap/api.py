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

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI
from fastapi.responses import JSONResponse
from fred_core import KeycloakUser, get_current_user

from control_plane_backend.bootstrap.dependencies import (
    BootstrapServiceDependencies,
    get_bootstrap_service_dependencies,
)
from control_plane_backend.bootstrap.schemas import (
    BootstrapAlreadyCompletedError,
    BootstrapAuthDisabledError,
    BootstrapPlatformAdminRequest,
    BootstrapPlatformAdminResponse,
    BootstrapRebacDisabledError,
    BootstrapTokenInvalidError,
)
from control_plane_backend.bootstrap.service import (
    bootstrap_platform_admin as bootstrap_platform_admin_from_service,
)

router = APIRouter(tags=["Bootstrap"])
BootstrapDependencies = Annotated[
    BootstrapServiceDependencies,
    Depends(get_bootstrap_service_dependencies),
]


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(BootstrapTokenInvalidError)
    async def bootstrap_token_invalid_handler(
        _request, exc: BootstrapTokenInvalidError
    ) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.exception_handler(BootstrapAlreadyCompletedError)
    async def bootstrap_already_completed_handler(
        _request, exc: BootstrapAlreadyCompletedError
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(BootstrapRebacDisabledError)
    async def bootstrap_rebac_disabled_handler(
        _request, exc: BootstrapRebacDisabledError
    ) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(BootstrapAuthDisabledError)
    async def bootstrap_auth_disabled_handler(
        _request, exc: BootstrapAuthDisabledError
    ) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})


@router.post(
    "/bootstrap/platform-admin",
    response_model=BootstrapPlatformAdminResponse,
    summary="One-time root platform-admin bootstrap (AUTHZ-07).",
    responses={
        403: {"description": "Invalid or disabled bootstrap secret."},
        409: {"description": "Root bootstrap already completed."},
        503: {
            "description": (
                "Authentication or ReBAC is disabled in this deployment — "
                "bootstrap cannot provide its two-independent-proofs guarantee."
            )
        },
    },
)
async def bootstrap_platform_admin(
    request: BootstrapPlatformAdminRequest,
    deps: BootstrapDependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> BootstrapPlatformAdminResponse:
    """
    Grant `platform_admin` to the calling identity on a fresh deployment.

    Why this endpoint exists:
    - a fresh deployment has no `platform_admin` yet, so no *authorized* route
      can bootstrap one. It still requires authentication (RFC Part 8, §42.2):
      a valid Keycloak JWT proves a real identity in this realm, and the
      deploy-time secret proves legitimate deploy-time access. Neither alone
      is sufficient, and the grant always targets the caller's own `sub` —
      this can never be used to promote a third party.

    How to use it:
    - log in once via the frontend/Keycloak directly, so your own identity
      exists and you hold a valid JWT
    - retrieve the deploy-time secret (Kubernetes Secret on GKE/AKS, an
      explicitly provided local file for the dev stack — `make
      bootstrap-token`)
    - call this endpoint, authenticated as yourself, with that secret
    - permanently refused once root bootstrap has ever completed (a durable
      marker, not a live admin count — surviving even a later loss of every
      `platform_admin`)

    Example:
    - `POST /control-plane/v1/bootstrap/platform-admin {"token": "..."}` with
      `Authorization: Bearer <your own JWT>`
    """
    return await bootstrap_platform_admin_from_service(user, request, deps)
