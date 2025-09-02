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
from typing import Annotated, Optional
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.params import Query

from app.core.stores.tags.base_tag_store import TagAlreadyExistsError, TagNotFoundError
from app.features.metadata.service import MetadataNotFound
from app.features.tag.service import TagService
from app.features.tag.structure import TagCreate, TagUpdate, TagWithItemsId, TagType
from fred_core import KeycloakUser, get_current_user

logger = logging.getLogger(__name__)


class TagController:
    """
    Controller for CRUD operations on Tag resource.
    Tags are used to group various items like documents and prompts.
    The TagController provides endpoints to easily retrieve tags with their items.
    """

    def __init__(self, router: APIRouter):
        self.service = TagService()

        def handle_exception(e: Exception) -> HTTPException:
            if isinstance(e, TagNotFoundError):
                return HTTPException(status_code=404, detail="Tag not found")
            if isinstance(e, TagAlreadyExistsError):
                return HTTPException(status_code=409, detail="Tag already exists")
            if isinstance(e, MetadataNotFound):
                return HTTPException(status_code=404, detail=str(e))
            logger.error(f"Internal server error: {e}", exc_info=True)
            return HTTPException(status_code=500, detail="Internal server error")

        self._register_routes(router, handle_exception)

    def _register_routes(self, router: APIRouter, handle_exception):
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
            try:
                return self.service.list_all_tags_for_user(
                    user,
                    tag_type=type,
                    path_prefix=path_prefix,
                    limit=limit,
                    offset=offset,
                )
            except Exception as e:
                raise handle_exception(e)

        @router.get(
            "/tags/{tag_id}",
            response_model=TagWithItemsId,
            response_model_exclude_none=True,
            tags=["Tags"],
            summary="Get a tag by ID",
        )
        async def get_tag(tag_id: str, user: KeycloakUser = Depends(get_current_user)):
            try:
                return self.service.get_tag_for_user(tag_id, user)
            except Exception as e:
                raise handle_exception(e)

        @router.post(
            "/tags",
            response_model=TagWithItemsId,
            response_model_exclude_none=True,
            status_code=status.HTTP_201_CREATED,
            tags=["Tags"],
            summary="Create a new tag",
        )
        async def create_tag(tag: TagCreate, user: KeycloakUser = Depends(get_current_user)):
            try:
                # Consider normalizing tag.path in the service if not already done
                logger.info(f"Creating tag: {tag} for user: {user.uid}")
                return self.service.create_tag_for_user(tag, user)
            except Exception as e:
                raise handle_exception(e)

        @router.put(
            "/tags/{tag_id}",
            response_model=TagWithItemsId,
            response_model_exclude_none=True,
            tags=["Tags"],
            summary="Update a tag (can rename/move via name/path)",
        )
        async def update_tag(tag_id: str, tag: TagUpdate, user: KeycloakUser = Depends(get_current_user)):
            try:
                return self.service.update_tag_for_user(tag_id, tag, user)
            except Exception as e:
                raise handle_exception(e)

        @router.delete(
            "/tags/{tag_id}",
            tags=["Tags"],
            status_code=status.HTTP_204_NO_CONTENT,
            summary="Delete a tag",
        )
        async def delete_tag(tag_id: str, user: KeycloakUser = Depends(get_current_user)):
            try:
                self.service.delete_tag_for_user(tag_id, user)
                return
            except Exception as e:
                raise handle_exception(e)
