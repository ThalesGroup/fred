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

from datetime import datetime
import logging
from uuid import uuid4
from typing import List

from app.application_context import ApplicationContext
from app.core.stores.prompts.base_prompt_store import PromptNotFoundError
from app.core.stores.tags.base_tag_store import TagNotFoundError
from app.features.prompts.structure import Prompt
from fred_core import KeycloakUser

from app.features.tag.structure import TagWithItemsId

logger = logging.getLogger(__name__)

class PromptService:
    """
    Service for managing Prompt objects, grouped by tags.
    """

    def __init__(self):
        context = ApplicationContext.get_instance()
        self._prompt_store = context.get_prompt_store()
        self._tag_store = context.get_tag_store()

    def get_prompt_in_tag(self, tag_id: str) -> list[Prompt]:
        """
        Return all prompt entries associated with a specific tag.
        """
        try:
            return self._prompt_store.get_prompt_in_tag(tag_id)
        
        except PromptNotFoundError:
            return []
        
        except Exception as e:
            logger.error(f"Error retrieving metadata for tag {tag_id}: {e}")
            raise
    
    # def list_all_prompt_tags(self, user: KeycloakUser) -> List[TagWithItemsId]:
    #     tags = self._tag_store.list_tags_for_user(user)
    #     prompt_list = self._prompt_store.list_prompts_for_user(user.uid)

    #     prompts_by_tag = {}
    #     for prompt in prompt_list:
    #         for tag_id in prompt.tags:
    #             prompts_by_tag.setdefault(tag_id, []).append(prompt)

    #     result = []
    #     for tag in tags:
    #         if tag.type.value != "prompt":
    #             continue
    #         prompts = prompts_by_tag.get(tag.id, [])
    #         prompt_ids = [p.id for p in prompts]
    #         result.append(TagWithItemsId.from_tag(tag, prompt_ids))
    #     return result

    def get_prompt_for_user(self, prompt_id: str, user: KeycloakUser) -> Prompt:
        return self._prompt_store.get_prompt_by_id(prompt_id)

    def create_prompt_for_user(self, prompt_data: Prompt, user: KeycloakUser) -> TagWithItemsId:
        now = datetime.now()
        prompt = Prompt(
            id=str(uuid4()),
            name=prompt_data.name,
            content=prompt_data.content,
            description=prompt_data.description,
            tags=prompt_data.tags,
            owner_id=user.uid,
            created_at=now,
            updated_at=now,
        )

        self._prompt_store.create_prompt(prompt)

        # For simplicity, associate with the first tag (should be of type "prompt")
        tag_id = prompt.tags[0] 
        try:
            tag = self._tag_store.get_tag_by_id(tag_id) 
            return TagWithItemsId.from_tag(tag, [prompt.id]) 
        except TagNotFoundError:
            raise ValueError(f"Tag with id '{tag_id}' not found for prompt '{prompt.id}'")

    def update_prompt_for_user(self, prompt_id: str, 
                               prompt_data: Prompt, 
                               user: KeycloakUser) -> Prompt:
        try:
            existing_prompt = self._prompt_store.get_prompt_by_id(prompt_id)
            if existing_prompt.owner_id != user.uid:
                raise PermissionError("User does not have permission to update this prompt.")

            updated_prompt = Prompt(
                id=prompt_id,
                name=prompt_data.name,
                content=prompt_data.content,
                description=prompt_data.description,
                tags=prompt_data.tags,
                owner_id=user.uid,
                created_at=existing_prompt.created_at,
                updated_at=datetime.now(),
            )

            return self._prompt_store.update_prompt(prompt_id, updated_prompt)
        except PromptNotFoundError:
            raise PromptNotFoundError(f"Prompt with id '{prompt_id}' not found.")
        except Exception as e:
            logger.error(f"Failed to update prompt '{prompt_id}': {e}")
            raise

    def remove_tag_from_prompt(self, prompt_id: str, tag_id: str) -> None:
        """
        Remove a tag from a prompt.
        """
        try:
            prompt = self._prompt_store.get_prompt_by_id(prompt_id)
            if tag_id in prompt.tags:
                prompt.tags.remove(tag_id)
                # if there is no more tags, we can remove the prompt
                if not prompt.tags:
                    self._prompt_store.delete_prompt(prompt_id)
                    logger.info(f"Prompt '{prompt_id}' deleted as it has no tags left.")
                else:
                    # Update the prompt with the remaining tags
                    prompt.updated_at = datetime.now()
                    self._prompt_store.update_prompt(prompt_id, prompt)
                    logger.info(f"Removed tag '{tag_id}' from prompt '{prompt_id}'")
            else:
                logger.error(f"Tag '{tag_id}' not found in prompt '{prompt_id}'")
        except PromptNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to remove tag '{tag_id}' from prompt '{prompt_id}': {e}")
            raise   

    def add_tag_to_prompt(self, prompt_id: str, tag_id: str) -> None:
        """
        Add a tag to a prompt.
        """
        try:
            prompt = self._prompt_store.get_prompt_by_id(prompt_id)
            if tag_id in prompt.tags:
                prompt.tags.remove(tag_id)
                # if there is no more tags, we can remove the prompt
                if not prompt.tags:
                    self._prompt_store.delete_prompt(prompt_id)
                    logger.info(f"Prompt '{prompt_id}' deleted as it has no tags left.")
                else:
                    # Update the prompt with the remaining tags
                    prompt.updated_at = datetime.now()
                    self._prompt_store.update_prompt(prompt_id, prompt)
                    logger.info(f"Removed tag '{tag_id}' from prompt '{prompt_id}'")
            else:
                logger.error(f"Tag '{tag_id}' not found in prompt '{prompt_id}'")
        except PromptNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to remove tag '{tag_id}' from prompt '{prompt_id}': {e}")
            raise  
