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
from uuid import uuid4
from typing import List

from app.application_context import ApplicationContext
from app.core.stores.tags.base_tag_store import TagNotFoundError
from app.features.prompts.structure import Prompt
from fred_core import KeycloakUser

from app.features.tag.structure import TagType, TagWithItemsId


class PromptService:
    """
    Service for managing Prompt objects, grouped by tags.
    """

    def __init__(self):
        context = ApplicationContext.get_instance()
        self._prompt_store = context.get_prompt_store()
        self._tag_store = context.get_tag_store()

    def list_all_prompts(self, user: KeycloakUser) -> List[TagWithItemsId]:
        tags = self._tag_store.list_tags_for_user(user, TagType.PROMPT)
        prompt_list = self._prompt_store.list_prompts_for_user(user.uid)

        prompts_by_tag = {}
        for prompt in prompt_list:
            for tag_id in prompt.tags:
                prompts_by_tag.setdefault(tag_id, []).append(prompt)

        result = []
        for tag in tags:
            if tag.type.value != "prompt":
                continue
            prompts = prompts_by_tag.get(tag.id, [])
            prompt_ids = [p.id for p in prompts]
            result.append(TagWithItemsId.from_tag(tag, prompt_ids))
        return result

    def get_prompt_for_user(self, prompt_id: str, user: KeycloakUser) -> TagWithItemsId:
        prompt = self._prompt_store.get_prompt_by_id(prompt_id)
        # Optional: assert ownership / access control
        tag_ids = prompt.tags
        tags = [self._tag_store.get_tag_by_id(tid) for tid in tag_ids if self._tag_store.get_tag_by_id(tid).type.value == "prompt"]

        if not tags:
            raise ValueError(f"No associated prompt library tag found for prompt '{prompt_id}'")

        tag = tags[0]  # Assuming one prompt library
        return TagWithItemsId.from_tag(tag, [prompt_id])

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
                               user: KeycloakUser) -> TagWithItemsId:
       raise ValueError("Not Implemented: Update operation for prompts is not supported yet.")

    def delete_prompt_for_user(self, tag_id: str, user: KeycloakUser) -> None:
        # Todo: check if user is authorized

        # Remove the tag ID from all documents that have this tag
        raise ValueError("Not Implemented: Delete operation for prompts is not supported yet.")
