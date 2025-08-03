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

from typing import List
import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.stores.tags.base_tag_store import TagAlreadyExistsError, TagNotFoundError
from app.features.metadata.service import MetadataNotFound
from app.features.tag.service import TagService
from app.features.tag.structure import TagCreate, TagUpdate, TagWithItemsId
from fred_core import KeycloakUser, get_current_user

logger = logging.getLogger(__name__)


class TagController:
    """
    Controller for CRUD operations on Tag resource.
    """

    def __init__(self, router: APIRouter):
        self.service = TagService()

        def handle_exception(e: Exception) -> HTTPException:
            if isinstance(e, TagNotFoundError):
                return HTTPException(status_code=404, detail="Tag not found")
            if isinstance(e, TagAlreadyExistsError):
                return HTTPException(status_code=409, detail="Tag already exists")
            # Invalid document id was passed
            if isinstance(e, MetadataNotFound):
                return HTTPException(status_code=404, detail=str(e))

            # Todo: handle authorization exception(s)
            # if isinstance(e, AuthorizationError):
            #     return HTTPException(status_code=403, detail="Not authorized to perform this tag operation")

            logger.error(f"Internal server error: {e}", exc_info=True)
            return HTTPException(status_code=500, detail="Internal server error")

        self._register_routes(router, handle_exception)

    def _register_routes(self, router: APIRouter, handle_exception):
        @router.get("/tags", response_model=List[TagWithItemsId], tags=["Tag"], summary="List all tags")
        async def list_tags(user: KeycloakUser = Depends(get_current_user)):
            try:
                return self.service.list_document_tags_for_user(user)
            except Exception as e:
                raise handle_exception(e)

        @router.get("/tags/{tag_id}", response_model=TagWithItemsId, tags=["Tag"], summary="Get a tag by ID")
        async def get_tag(tag_id: str, user: KeycloakUser = Depends(get_current_user)):
            try:
                return self.service.get_tag_for_user(tag_id, user)
            except Exception as e:
                raise handle_exception(e)

        @router.post("/tags", response_model=TagWithItemsId, tags=["Tag"], summary="Create a new tag")
        async def create_tag(tag: TagCreate, user: KeycloakUser = Depends(get_current_user)):
            try:
                return self.service.create_tag_for_user(tag, user)
            except Exception as e:
                raise handle_exception(e)

        @router.put("/tags/{tag_id}", response_model=TagWithItemsId, tags=["Tag"], summary="Update a tag")
        async def update_tag(tag_id: str, tag: TagUpdate, user: KeycloakUser = Depends(get_current_user)):
            try:
                return self.service.update_tag_for_user(tag_id, tag, user)
            except Exception as e:
                raise handle_exception(e)

        @router.delete("/tags/{tag_id}", tags=["Tag"], status_code=status.HTTP_204_NO_CONTENT, summary="Delete a tag")
        async def delete_tag(tag_id: str, user: KeycloakUser = Depends(get_current_user)):
            try:
                self.service.delete_tag_for_user(tag_id, user)
                return
            except Exception as e:
                raise handle_exception(e)
