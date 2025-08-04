# Copyright Thales 2025
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
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

from fastapi import APIRouter, Depends, HTTPException
from app.core.stores.prompts.base_prompt_store import PromptNotFoundError, PromptAlreadyExistsError
from fred_core import KeycloakUser, get_current_user

from app.features.prompts.service import PromptService
from app.features.prompts.structure import Prompt
from app.features.tag.structure import TagWithItemsId

logger = logging.getLogger(__name__)


class PromptController:
    """
    Controller for managing Prompt objects (CRUD).
    """

    def __init__(self, router: APIRouter):
        self.service = PromptService()

        def handle_exception(e: Exception) -> HTTPException:
            if isinstance(e, PromptNotFoundError):
                return HTTPException(status_code=404, detail="Prompt not found")
            if isinstance(e, PromptAlreadyExistsError):
                return HTTPException(status_code=409, detail="Prompt already exists")

            logger.error(f"Internal server error: {e}", exc_info=True)
            return HTTPException(status_code=500, detail="Internal server error")

        self._register_routes(router, handle_exception)

    def _register_routes(self, router: APIRouter, handle_exception):
        @router.get("/prompts/{prompt_id}", response_model=Prompt, tags=["Prompt"], summary="Get a prompt by ID")
        async def get_prompt(prompt_id: str, user: KeycloakUser = Depends(get_current_user)) -> Prompt:
            try:
                return self.service.get_prompt_for_user(prompt_id, user)
            except Exception as e:
                raise handle_exception(e)

        @router.post("/prompts", response_model=TagWithItemsId, tags=["Prompt"], summary="Create a new prompt")
        async def create_prompt(prompt_data: Prompt, user: KeycloakUser = Depends(get_current_user)) -> TagWithItemsId:
            try:
                return self.service.create_prompt_for_user(prompt_data, user)
            except Exception as e:
                raise handle_exception(e)

        @router.put("/prompts/{prompt_id}", response_model=Prompt, tags=["Prompt"], summary="Update an existing prompt")
        async def update_prompt(prompt_id: str, prompt_data: Prompt, user: KeycloakUser = Depends(get_current_user)) -> Prompt:
            try:
                return self.service.update_prompt_for_user(prompt_id, prompt_data, user)
            except Exception as e:
                raise handle_exception(e)
