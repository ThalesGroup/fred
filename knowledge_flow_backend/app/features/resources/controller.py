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


import logging
from typing import List
from fastapi.params import Query
from typing_extensions import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from fred_core import KeycloakUser, get_current_user

from app.core.stores.resources.base_resource_store import (
    ResourceNotFoundError,
    ResourceAlreadyExistsError,
)
from app.features.resources.service import ResourceService
from app.features.resources.structures import Resource, ResourceCreate, ResourceKind, ResourceUpdate

logger = logging.getLogger(__name__)

class ResourceController:
    """
    Controller for managing Resource objects (CRUD).
    A resource can be of type 'prompt' or 'template'.
    """

    def __init__(self, router: APIRouter):
        self.service = ResourceService()

        def handle_exception(e: Exception) -> HTTPException:
            if isinstance(e, ResourceNotFoundError):
                return HTTPException(status_code=404, detail="Resource not found")
            if isinstance(e, ResourceAlreadyExistsError):
                return HTTPException(status_code=409, detail="Resource already exists")

            logger.error(f"Internal server error: {e}", exc_info=True)
            return HTTPException(status_code=500, detail="Internal server error")

        self._register_routes(router, handle_exception)

    def _register_routes(self, router: APIRouter, handle_exception):
        @router.post(
            "/resources",
            response_model=Resource,
            response_model_exclude_none=True,
            status_code=status.HTTP_201_CREATED,
            summary="Create a resource (prompt/template) and attach it to a library.",
        )
        async def create_resource(
            library_tag_id: Annotated[str, Query(description="Library tag id to attach this resource to")],
            payload: ResourceCreate = Body(...),
            user: KeycloakUser = Depends(get_current_user),
        ) -> Resource:
            try:
                return self.service.create(library_tag_id=library_tag_id, payload=payload, user=user)
            except Exception as e:
                raise handle_exception(e)

        @router.put(
            "/resources/{resource_id}",
            response_model=Resource,
            response_model_exclude_none=True,
            summary="Update a resource (content/metadata).",
        )
        async def update_resource(
            resource_id: str,
            payload: ResourceUpdate = Body(...),
            user: KeycloakUser = Depends(get_current_user),
        ) -> Resource:
            try:
                return self.service.update(resource_id=resource_id, payload=payload, user=user)
            except Exception as e:
                raise handle_exception(e)

        @router.get(
            "/resources/{resource_id}",
            response_model=Resource,
            response_model_exclude_none=True,
            summary="Get a resource by id.",
        )
        async def get_resource(
            resource_id: str,
            user: KeycloakUser = Depends(get_current_user),
        ) -> Resource:
            try:
                return self.service.get(resource_id=resource_id, user=user)
            except Exception as e:
                raise handle_exception(e)

        @router.get(
            "/resources",
            response_model=List[Resource],
            response_model_exclude_none=True,
            summary="List all resources for a kind (prompt|template).",
        )
        async def list_resources_by_kind(
            kind: Annotated[ResourceKind, Query(description="prompt | template")],
            user: KeycloakUser = Depends(get_current_user),
        ) -> List[Resource]:
            try:
                return self.service.list_resources_by_kind(kind=kind)
            except Exception as e:
                raise handle_exception(e)

        @router.delete(
            "/resources/{resource_id}",
            summary="Delete a resource by id.",
        )
        async def delete_resource(
            resource_id: str,
            user: KeycloakUser = Depends(get_current_user),
        ) -> None:
            try:
                self.service.delete(resource_id=resource_id)
            except Exception as e:
                raise handle_exception(e)