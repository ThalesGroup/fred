from typing import List

from fastapi import APIRouter, Depends, HTTPException

from app.core.stores.tags.base_tag_store import TagAlreadyExistsError, TagNotFoundError
from app.features.tag.service import TagService
from app.features.tag.structure import Tag, TagCreate, TagUpdate
from fred_core import KeycloakUser, get_current_user

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

            # Todo: handle authorization exception
            # if isinstance(e, AuthorizationError):
            #     return HTTPException(status_code=403, detail="Not authorized to perform this tag operation")

            return HTTPException(status_code=500, detail="Internal server error")

        self._register_routes(router, handle_exception)

    def _register_routes(self, router: APIRouter, handle_exception):
        @router.get("/tags", response_model=List[Tag], tags=["Tag"], summary="List all tags")
        async def list_tags(user: KeycloakUser = Depends(get_current_user)):
            try:
                return self.service.list_tags_for_user(user)
            except Exception as e:
                raise handle_exception(e)

        @router.get("/tags/{tag_id}", response_model=Tag, tags=["Tag"], summary="Get a tag by ID")
        async def get_tag(tag_id: str, user: KeycloakUser = Depends(get_current_user)):
            try:
                return self.service.get_tag_for_user(tag_id, user)
            except Exception as e:
                raise handle_exception(e)

        @router.post("/tags", response_model=Tag, tags=["Tag"], summary="Create a new tag")
        async def create_tag(tag: TagCreate, user: KeycloakUser = Depends(get_current_user)):
            try:
                return self.service.create_tag_for_user(tag, user)
            except Exception as e:
                raise handle_exception(e)

        @router.put("/tags/{tag_id}", response_model=Tag, tags=["Tag"], summary="Update a tag")
        async def update_tag(tag_id: str, tag: TagUpdate, user: KeycloakUser = Depends(get_current_user)):
            try:
                return self.service.update_tag_for_user(tag_id, tag, user)
            except Exception as e:
                raise handle_exception(e)

        @router.delete("/tags/{tag_id}", tags=["Tag"], summary="Delete a tag")
        async def delete_tag(tag_id: str, user: KeycloakUser = Depends(get_current_user)):
            try:
                self.service.delete_tag_for_user(tag_id, user)
                return {"status": "success", "message": f"Tag {tag_id} deleted"}
            except Exception as e:
                raise handle_exception(e)
