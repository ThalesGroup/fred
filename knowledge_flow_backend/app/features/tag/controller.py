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

# Copyright Thales 2025
import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, FastAPI, Request, status
from fastapi.params import Query
from fastapi.responses import JSONResponse
from fred_core import KeycloakUser, get_current_user

from app.core.stores.tags.base_tag_store import TagAlreadyExistsError, TagNotFoundError
from app.features.metadata.service import MetadataNotFound
from app.features.tag.service import TagService
from app.features.tag.structure import TagCreate, TagShareRequest, TagType, TagUpdate, TagWithItemsId

logger = logging.getLogger(__name__)


class TagController:
    """
    Controller for CRUD operations on Tag resource.
    Tags are used to group various items like documents and prompts.
    The TagController provides endpoints to easily retrieve tags with their items.
    """

    def __init__(self, app: FastAPI, router: APIRouter):
        self.service = TagService()
        self._register_exception_handlers(app)
        self._register_routes(router)

    def _register_exception_handlers(self, app: FastAPI):
        """Register specific exception handlers for tag-related exceptions."""

        @app.exception_handler(TagNotFoundError)
        async def tag_not_found_handler(request: Request, exc: TagNotFoundError) -> JSONResponse:
            return JSONResponse(status_code=404, content={"detail": "Tag not found"})

        @app.exception_handler(TagAlreadyExistsError)
        async def tag_already_exists_handler(request: Request, exc: TagAlreadyExistsError) -> JSONResponse:
            return JSONResponse(status_code=409, content={"detail": "Tag already exists"})

        @app.exception_handler(MetadataNotFound)
        async def metadata_not_found_handler(request: Request, exc: MetadataNotFound) -> JSONResponse:
            return JSONResponse(status_code=404, content={"detail": str(exc)})

    def _register_routes(self, router: APIRouter):
        @router.get(
            "/tags",
            response_model=list[TagWithItemsId],
            response_model_exclude_none=True,
            tags=["Tags"],
            summary=("List tags (optionally filter by type or path prefix). Supports pagination to avoid huge payloads."),
        )
        async def list_all_tags(
            type: Annotated[Optional[TagType], Query(description="Filter by tag type")] = None,
            path_prefix: Annotated[Optional[str], Query(description="Filter by hierarchical path prefix, e.g. 'Sales' or 'Sales/HR'")] = None,
            limit: Annotated[int, Query(ge=1, le=10000, description="Max items to return")] = 10000,
            offset: Annotated[int, Query(ge=0, description="Items to skip")] = 0,
            user: KeycloakUser = Depends(get_current_user),
        ) -> list[TagWithItemsId]:
            return self.service.list_all_tags_for_user(
                user,
                tag_type=type,
                path_prefix=path_prefix,
                limit=limit,
                offset=offset,
            )

        @router.get(
            "/tags/{tag_id}",
            response_model=TagWithItemsId,
            response_model_exclude_none=True,
            tags=["Tags"],
            summary="Get a tag by ID",
        )
        async def get_tag(tag_id: str, user: KeycloakUser = Depends(get_current_user)):
            return self.service.get_tag_for_user(tag_id, user)

        @router.post(
            "/tags",
            response_model=TagWithItemsId,
            response_model_exclude_none=True,
            status_code=status.HTTP_201_CREATED,
            tags=["Tags"],
            summary="Create a new tag",
        )
        async def create_tag(tag: TagCreate, user: KeycloakUser = Depends(get_current_user)):
            # Consider normalizing tag.path in the service if not already done
            logger.info(f"Creating tag: {tag} for user: {user.uid}")
            return self.service.create_tag_for_user(tag, user)

        @router.put(
            "/tags/{tag_id}",
            response_model=TagWithItemsId,
            response_model_exclude_none=True,
            tags=["Tags"],
            summary="Update a tag (can rename/move via name/path)",
        )
        async def update_tag(tag_id: str, tag: TagUpdate, user: KeycloakUser = Depends(get_current_user)):
            return self.service.update_tag_for_user(tag_id, tag, user)

        @router.delete(
            "/tags/{tag_id}",
            tags=["Tags"],
            status_code=status.HTTP_204_NO_CONTENT,
            summary="Delete a tag",
        )
        async def delete_tag(tag_id: str, user: KeycloakUser = Depends(get_current_user)):
            self.service.delete_tag_for_user(tag_id, user)

        @router.post(
            "/tags/{tag_id}/share",
            status_code=status.HTTP_204_NO_CONTENT,
            tags=["Tags"],
            summary="Share a tag with another user",
        )
        async def share_tag(tag_id: str, share_request: TagShareRequest, user: KeycloakUser = Depends(get_current_user)):
            self.service.share_tag_with_user(user, tag_id, share_request.target_user_id, share_request.relation)

        @router.delete(
            "/tags/{tag_id}/share/{target_user_id}",
            status_code=status.HTTP_204_NO_CONTENT,
            tags=["Tags"],
            summary="Stop sharing a tag with a user",
        )
        async def unshare_tag(tag_id: str, target_user_id: str, user: KeycloakUser = Depends(get_current_user)):
            self.service.unshare_tag_with_user(user, tag_id, target_user_id)
