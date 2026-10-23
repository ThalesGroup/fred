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

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fred_core import KeycloakUser, get_current_user
from fred_core.security.models import AuthorizationError

from control_plane_backend.app.route_errors import map_error
from control_plane_backend.model_discovery import service
from control_plane_backend.model_discovery.schemas import (
    DiscoverySourceStatus,
    ModelDiscoveryStatus,
    PodChatDefaults,
    PodChatDefaultStatus,
    SetDiscoveryUrlRequest,
    SetPodChatDefaultRequest,
    SetPodChatFallbackRequest,
)
from control_plane_backend.model_discovery.service import DiscoveryRefreshError
from control_plane_backend.product.dependencies import (
    ProductServiceDependencies,
    get_product_service_dependencies,
)

router = APIRouter(tags=["Capabilities"])
Dependencies = Annotated[
    ProductServiceDependencies, Depends(get_product_service_dependencies)
]


@router.get("/admin/model-discovery", response_model=ModelDiscoveryStatus)
async def get_model_discovery(
    deps: Dependencies, user: KeycloakUser = Depends(get_current_user)
) -> ModelDiscoveryStatus:
    try:
        return await service.get_status(user, deps)
    except AuthorizationError as exc:
        raise map_error(exc) from exc


@router.delete(
    "/admin/model-discovery/{source_id}/removed-model",
    response_model=DiscoverySourceStatus,
)
async def dismiss_removed_model(
    source_id: Annotated[str, Path(min_length=1, max_length=64)],
    model_id: Annotated[str, Query(min_length=1, max_length=256)],
    deps: Dependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> DiscoverySourceStatus:
    try:
        return await service.dismiss_removed_model(
            user, deps, source_id=source_id, model_id=model_id
        )
    except AuthorizationError as exc:
        raise map_error(exc) from exc
    except KeyError:
        raise HTTPException(status_code=404, detail="Removed model not found") from None


@router.get("/admin/pod-chat-defaults", response_model=PodChatDefaults)
async def get_pod_chat_defaults(
    request: Request,
    deps: Dependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> PodChatDefaults:
    try:
        return await service.get_pod_chat_defaults(
            user, deps, authorization=request.headers.get("Authorization")
        )
    except AuthorizationError as exc:
        raise map_error(exc) from exc


@router.put(
    "/admin/pod-chat-defaults/{runtime_id}", response_model=PodChatDefaultStatus
)
async def put_pod_chat_default(
    runtime_id: Annotated[str, Path(min_length=1, max_length=160)],
    body: SetPodChatDefaultRequest,
    request: Request,
    deps: Dependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> PodChatDefaultStatus:
    try:
        return await service.set_pod_chat_default(
            user,
            deps,
            runtime_id=runtime_id,
            profile_id=body.profile_id,
            authorization=request.headers.get("Authorization"),
        )
    except AuthorizationError as exc:
        raise map_error(exc) from exc
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown agent pod") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except DiscoveryRefreshError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None


@router.delete(
    "/admin/pod-chat-defaults/{runtime_id}", response_model=PodChatDefaultStatus
)
async def clear_pod_chat_default(
    runtime_id: Annotated[str, Path(min_length=1, max_length=160)],
    request: Request,
    deps: Dependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> PodChatDefaultStatus:
    try:
        return await service.delete_pod_chat_default(
            user,
            deps,
            runtime_id=runtime_id,
            authorization=request.headers.get("Authorization"),
        )
    except AuthorizationError as exc:
        raise map_error(exc) from exc
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown agent pod") from None


@router.put(
    "/admin/pod-chat-defaults/{runtime_id}/fallback",
    response_model=PodChatDefaultStatus,
)
async def put_pod_chat_fallback(
    runtime_id: Annotated[str, Path(min_length=1, max_length=160)],
    body: SetPodChatFallbackRequest,
    request: Request,
    deps: Dependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> PodChatDefaultStatus:
    try:
        return await service.set_pod_chat_fallback(
            user,
            deps,
            runtime_id=runtime_id,
            profile_id=body.profile_id,
            authorization=request.headers.get("Authorization"),
        )
    except AuthorizationError as exc:
        raise map_error(exc) from exc
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown agent pod") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except DiscoveryRefreshError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None


@router.delete(
    "/admin/pod-chat-defaults/{runtime_id}/fallback",
    response_model=PodChatDefaultStatus,
)
async def clear_pod_chat_fallback(
    runtime_id: Annotated[str, Path(min_length=1, max_length=160)],
    request: Request,
    deps: Dependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> PodChatDefaultStatus:
    try:
        return await service.delete_pod_chat_fallback(
            user,
            deps,
            runtime_id=runtime_id,
            authorization=request.headers.get("Authorization"),
        )
    except AuthorizationError as exc:
        raise map_error(exc) from exc
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown agent pod") from None


@router.post("/admin/model-discovery/refresh", response_model=ModelDiscoveryStatus)
async def refresh_model_discovery(
    request: Request,
    deps: Dependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> ModelDiscoveryStatus:
    try:
        return await service.refresh(
            user, deps, authorization=request.headers.get("Authorization")
        )
    except AuthorizationError as exc:
        raise map_error(exc) from exc


@router.get("/admin/model-discovery/detail", response_model=dict)
async def get_model_discovery_detail(
    request: Request,
    deps: Dependencies,
    source_id: Annotated[str, Query(min_length=1, max_length=64)],
    model_id: Annotated[str, Query(min_length=1, max_length=256)],
    runtime_id: str | None = None,
    user: KeycloakUser = Depends(get_current_user),
) -> dict:
    try:
        return await service.get_model_detail(
            user,
            deps,
            source_id=source_id,
            model_id=model_id,
            runtime_id=runtime_id,
            authorization=request.headers.get("Authorization"),
        )
    except AuthorizationError as exc:
        raise map_error(exc) from exc
    except KeyError:
        raise HTTPException(
            status_code=404, detail="Model detail is unavailable"
        ) from None


@router.put(
    "/admin/model-discovery/{source_id}/url", response_model=DiscoverySourceStatus
)
async def put_model_discovery_url(
    source_id: Annotated[str, Path(min_length=1, max_length=64)],
    body: SetDiscoveryUrlRequest,
    request: Request,
    deps: Dependencies,
    user: KeycloakUser = Depends(get_current_user),
) -> DiscoverySourceStatus:
    try:
        return await service.set_url(
            user,
            deps,
            source_id=source_id,
            url=body.url,
            authorization=request.headers.get("Authorization"),
        )
    except AuthorizationError as exc:
        raise map_error(exc) from exc
    except KeyError:
        raise HTTPException(
            status_code=404, detail="Unknown discovery source"
        ) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except DiscoveryRefreshError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
